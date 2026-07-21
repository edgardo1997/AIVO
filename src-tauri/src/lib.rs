use rand::{rngs::OsRng, RngCore};
use std::collections::HashMap;
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

fn drain_complete_ndjson_lines(
    pending: &mut Vec<u8>,
    chunk: &[u8],
) -> Result<Vec<String>, &'static str> {
    pending.extend_from_slice(chunk);

    let mut lines = Vec::new();
    let mut consumed = 0;
    for (index, byte) in pending.iter().enumerate() {
        if *byte != b'\n' {
            continue;
        }
        let text = std::str::from_utf8(&pending[consumed..=index])
            .map_err(|_| "Sentinel response stream returned invalid UTF-8")?;
        lines.push(text.to_owned());
        consumed = index + 1;
    }
    if consumed > 0 {
        pending.drain(..consumed);
    }
    Ok(lines)
}

fn finish_ndjson_stream(pending: &mut Vec<u8>) -> Result<Option<String>, &'static str> {
    if pending.is_empty() {
        return Ok(None);
    }
    let text = std::str::from_utf8(pending)
        .map_err(|_| "Sentinel response stream ended with incomplete or invalid UTF-8")?
        .to_owned();
    pending.clear();
    Ok(Some(text))
}

#[cfg(test)]
mod stream_utf8_tests {
    use super::{drain_complete_ndjson_lines, finish_ndjson_stream};

    #[test]
    fn preserves_enye_split_between_chunks() {
        let bytes = "España\n".as_bytes();
        let split = bytes.iter().position(|byte| *byte == 0xC3).unwrap() + 1;
        let mut pending = Vec::new();

        let first = drain_complete_ndjson_lines(&mut pending, &bytes[..split]).unwrap();
        let second = drain_complete_ndjson_lines(&mut pending, &bytes[split..]).unwrap();

        assert!(first.is_empty());
        assert_eq!(second, vec!["España\n"]);
        assert!(pending.is_empty());
    }

    #[test]
    fn preserves_emoji_split_between_chunks() {
        let bytes = "ok 😁 listo\n".as_bytes();
        let emoji = bytes.iter().position(|byte| *byte == 0xF0).unwrap();
        let mut pending = Vec::new();

        let first = drain_complete_ndjson_lines(&mut pending, &bytes[..emoji + 2]).unwrap();
        let second = drain_complete_ndjson_lines(&mut pending, &bytes[emoji + 2..]).unwrap();

        assert!(first.is_empty());
        assert_eq!(second, vec!["ok 😁 listo\n"]);
        assert!(pending.is_empty());
    }

    #[test]
    fn rejects_truncated_utf8_at_end_of_stream() {
        let mut pending = vec![0xF0, 0x9F];
        assert!(finish_ndjson_stream(&mut pending).is_err());
    }

    #[test]
    fn emits_only_complete_ndjson_lines() {
        let mut pending = Vec::new();
        let first = drain_complete_ndjson_lines(&mut pending, b"{\"a\":1}\n{\"b\"").unwrap();
        let second = drain_complete_ndjson_lines(&mut pending, b":2}\n").unwrap();

        assert_eq!(first, vec!["{\"a\":1}\n"]);
        assert_eq!(second, vec!["{\"b\":2}\n"]);
        assert!(pending.is_empty());
    }
}
use tauri::ipc::Channel;
use tauri::Manager;

#[derive(serde::Serialize)]
struct SidecarResponse {
    status: u16,
    body: String,
}

struct SidecarProcess(Mutex<Option<Child>>);
struct SidecarSessionToken(String);
struct ActiveStreams(Mutex<HashMap<String, tokio::sync::watch::Sender<bool>>>);

#[tauri::command]
fn get_sidecar_port() -> u16 {
    8765
}

#[tauri::command]
fn get_sidecar_session_token(state: tauri::State<'_, SidecarSessionToken>) -> String {
    state.0.clone()
}

#[tauri::command]
async fn sidecar_request(
    state: tauri::State<'_, SidecarSessionToken>,
    method: String,
    path: String,
    body: Option<serde_json::Value>,
) -> Result<SidecarResponse, String> {
    if !path.starts_with('/') || path.starts_with("//") {
        return Err("Invalid local API path".into());
    }
    let method = reqwest::Method::from_bytes(method.as_bytes())
        .map_err(|_| "Invalid local API method".to_string())?;
    if !matches!(
        method,
        reqwest::Method::GET
            | reqwest::Method::POST
            | reqwest::Method::PUT
            | reqwest::Method::PATCH
            | reqwest::Method::DELETE
    ) {
        return Err("Unsupported local API method".into());
    }
    let client = reqwest::Client::builder()
        // Conversation and orchestration have their own shorter recovery limits.
        // Keep the UI from appearing frozen if the local service ever regresses.
        .timeout(Duration::from_secs(45))
        .build()
        .map_err(|_| "Sentinel local connection is unavailable".to_string())?;
    let mut request = client
        .request(method, format!("http://127.0.0.1:8765{path}"))
        .bearer_auth(&state.0);
    if let Some(payload) = body {
        request = request.json(&payload);
    }
    let response = request
        .send()
        .await
        .map_err(|_| "Sentinel local connection is unavailable".to_string())?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    Ok(SidecarResponse { status, body })
}

#[tauri::command]
async fn sidecar_stream(
    state: tauri::State<'_, SidecarSessionToken>,
    active_streams: tauri::State<'_, ActiveStreams>,
    path: String,
    body: serde_json::Value,
    request_id: String,
    on_event: Channel<String>,
) -> Result<(), String> {
    if !path.starts_with('/') || path.starts_with("//") {
        return Err("Invalid local API path".into());
    }
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(75))
        .build()
        .map_err(|_| "Sentinel local streaming is unavailable".to_string())?;
    if request_id.is_empty() || request_id.len() > 80 {
        return Err("Invalid stream request id".into());
    }
    let (cancel_tx, mut cancel_rx) = tokio::sync::watch::channel(false);
    active_streams
        .0
        .lock()
        .map_err(|_| "Sentinel stream registry is unavailable".to_string())?
        .insert(request_id.clone(), cancel_tx);
    let request = client
        .post(format!("http://127.0.0.1:8765{path}"))
        .bearer_auth(&state.0)
        .json(&body);
    let mut response = tokio::select! {
        result = request.send() => match result {
            Ok(response) => response,
            Err(_) => {
                if let Ok(mut streams) = active_streams.0.lock() {
                    streams.remove(&request_id);
                }
                return Err("Sentinel local streaming is unavailable".to_string());
            }
        },
        _ = cancel_rx.changed() => {
            if let Ok(mut streams) = active_streams.0.lock() {
                streams.remove(&request_id);
            }
            return Ok(());
        }
    };

    if !response.status().is_success() {
        let status = response.status().as_u16();
        let detail = response.text().await.unwrap_or_default();
        if let Ok(mut streams) = active_streams.0.lock() {
            streams.remove(&request_id);
        }
        return Err(if detail.is_empty() {
            format!("Sentinel streaming request failed ({status})")
        } else {
            detail
        });
    }

    let mut stream_error: Option<String> = None;
    let mut pending_ndjson: Vec<u8> = Vec::new();
    let mut cancelled = false;
    loop {
        let chunk = tokio::select! {
            result = response.chunk() => match result {
                Ok(chunk) => chunk,
                Err(_) => {
                    stream_error = Some("Sentinel response stream was interrupted".to_string());
                    break;
                }
            },
            _ = cancel_rx.changed() => {
                cancelled = true;
                break;
            },
        };
        let Some(chunk) = chunk else { break };
        let lines = match drain_complete_ndjson_lines(&mut pending_ndjson, &chunk) {
            Ok(lines) => lines,
            Err(error) => {
                stream_error = Some(error.to_string());
                break;
            }
        };
        for text in lines {
            if on_event.send(text).is_err() {
                stream_error =
                    Some("Sentinel interface stopped receiving the response".to_string());
                break;
            }
        }
        if stream_error.is_some() {
            break;
        }
    }
    if stream_error.is_none() && !cancelled {
        match finish_ndjson_stream(&mut pending_ndjson) {
            Ok(Some(text)) => {
                if on_event.send(text).is_err() {
                    stream_error =
                        Some("Sentinel interface stopped receiving the response".to_string());
                }
            }
            Ok(None) => {}
            Err(error) => stream_error = Some(error.to_string()),
        }
    }
    if let Ok(mut streams) = active_streams.0.lock() {
        streams.remove(&request_id);
    }
    stream_error.map_or(Ok(()), Err)
}

#[tauri::command]
fn cancel_sidecar_stream(
    active_streams: tauri::State<'_, ActiveStreams>,
    request_id: String,
) -> bool {
    let sender = active_streams
        .0
        .lock()
        .ok()
        .and_then(|mut streams| streams.remove(&request_id));
    sender.is_some_and(|sender| sender.send(true).is_ok())
}

fn generate_session_token() -> String {
    let mut bytes = [0_u8; 32];
    OsRng.fill_bytes(&mut bytes);
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn find_python() -> Option<&'static str> {
    for candidate in &["python", "python3", "py"] {
        if let Ok(output) = Command::new(candidate)
            .arg("--version")
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .output()
        {
            let out = String::from_utf8_lossy(&output.stdout);
            let err = String::from_utf8_lossy(&output.stderr);
            // Microsoft Store stub exits 0 but outputs no "Python" string.
            // Real Python always includes "Python" in --version output.
            if out.contains("Python") || err.contains("Python") {
                return Some(candidate);
            }
        }
    }
    None
}

fn wait_for_sidecar(timeout_secs: u64, session_token: &str) -> bool {
    let deadline = std::time::Instant::now() + Duration::from_secs(timeout_secs);
    while std::time::Instant::now() < deadline {
        if let Ok(mut stream) = TcpStream::connect_timeout(
            &"127.0.0.1:8765".parse().unwrap(),
            Duration::from_millis(200),
        ) {
            let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
            let request = format!(
                "GET /api/health HTTP/1.1\r\nHost: 127.0.0.1:8765\r\nAuthorization: Bearer {session_token}\r\nConnection: close\r\n\r\n"
            );
            if stream.write_all(request.as_bytes()).is_ok() {
                let mut response = String::new();
                if stream.read_to_string(&mut response).is_ok()
                    && response.starts_with("HTTP/1.1 200")
                    && response.contains("\"status\":\"ok\"")
                {
                    return true;
                }
            }
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    false
}

fn find_bundled_sidecar(app: &tauri::AppHandle) -> Option<PathBuf> {
    // Development must run the current Python sources. A stale packaged binary
    // can otherwise pass health checks while exposing an older API contract.
    if cfg!(debug_assertions) {
        return None;
    }
    let prod = app.path().resource_dir().ok()?;
    let exe = prod.join("sidecar").join("sidecar.exe");
    if exe.exists() {
        return Some(exe);
    }
    None
}

fn find_sidecar_dir(app: &tauri::AppHandle) -> Option<PathBuf> {
    let prod = app.path().resource_dir().ok().map(|d| d.join("sidecar"));
    if let Some(ref p) = prod {
        if p.join("main.py").exists() {
            return Some(p.clone());
        }
    }
    let dev = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .map(|p| p.join("sidecar"));
    if let Some(ref p) = dev {
        if p.join("main.py").exists() || p.join("dist").join("sidecar.exe").exists() {
            return Some(p.clone());
        }
    }
    let cwd = std::env::current_dir().ok().map(|d| d.join("sidecar"));
    if let Some(ref p) = cwd {
        if p.join("main.py").exists() {
            return Some(p.clone());
        }
    }
    None
}

fn start_sidecar(app: &tauri::AppHandle, session_token: &str) {
    let database_path = app
        .path()
        .app_data_dir()
        .unwrap_or_else(|_| std::env::temp_dir().join("Sentinel"))
        .join("sentinel.db");
    let (sidecar_exe, sidecar_dir) = if let Some(exe) = find_bundled_sidecar(app) {
        eprintln!("[Sentinel] Found bundled sidecar.exe");
        (exe.clone(), exe.parent().unwrap().to_path_buf())
    } else if let Some(dir) = find_sidecar_dir(app) {
        let dev_exe = dir.join("dist").join("sidecar.exe");
        if dev_exe.exists() && !cfg!(debug_assertions) {
            eprintln!("[Sentinel] Found dev sidecar.exe at {:?}", dev_exe);
            (dev_exe, dir.join("dist"))
        } else {
            // Fallback: run via python
            let python = match find_python() {
                Some(p) => p,
                None => {
                    eprintln!("[Sentinel] Python not found. Install Python 3.12+ or build sidecar.exe with PyInstaller.");
                    return;
                }
            };
            eprintln!("[Sentinel] Starting sidecar with {} from {:?}", python, dir);
            match Command::new(python)
                .arg("-u")
                .arg("-m")
                .arg("uvicorn")
                .arg("main:app")
                .arg("--host")
                .arg("127.0.0.1")
                .arg("--port")
                .arg("8765")
                .arg("--log-level")
                .arg("warning")
                .env("SENTINEL_SESSION_TOKEN", session_token)
                .env("SENTINEL_DB_PATH", &database_path)
                .env("PYTHONPATH", dir.parent().unwrap_or(&dir))
                .current_dir(&dir)
                // Python already writes rotating diagnostics to Sentinel's log directory.
                // Unread pipes can fill and deadlock a long-running child process.
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
            {
                Ok(child) => {
                    let state = app.state::<SidecarProcess>();
                    *state.0.lock().unwrap() = Some(child);
                    eprintln!("[Sentinel] Sidecar process started, waiting for it to be ready...");
                    if wait_for_sidecar(15, session_token) {
                        eprintln!("[Sentinel] Sidecar ready on port 8765");
                    } else {
                        eprintln!("[Sentinel] Sidecar did not become ready within 15s");
                    }
                }
                Err(e) => eprintln!("[Sentinel] Failed to start sidecar: {}", e),
            }
            return;
        }
    } else {
        eprintln!("[Sentinel] sidecar/ directory not found. Check your installation.");
        return;
    };

    // Launch bundled sidecar.exe
    eprintln!(
        "[Sentinel] Starting bundled sidecar.exe from {:?}",
        sidecar_dir
    );
    match Command::new(&sidecar_exe)
        .env("SENTINEL_SESSION_TOKEN", session_token)
        .env("SENTINEL_DB_PATH", &database_path)
        .current_dir(&sidecar_dir)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
    {
        Ok(child) => {
            let state = app.state::<SidecarProcess>();
            *state.0.lock().unwrap() = Some(child);
            eprintln!("[Sentinel] sidecar.exe started, waiting for it to be ready...");
            if wait_for_sidecar(15, session_token) {
                eprintln!("[Sentinel] sidecar.exe ready on port 8765");
            } else {
                eprintln!("[Sentinel] sidecar.exe did not become ready within 15s");
            }
        }
        Err(e) => {
            eprintln!("[Sentinel] Failed to start sidecar.exe: {}", e);
        }
    }
}

fn kill_sidecar(app: &tauri::AppHandle) {
    let state = app.state::<SidecarProcess>();
    let mut guard = state.0.lock().unwrap();
    if let Some(mut child) = guard.take() {
        eprintln!("[Sentinel] Stopping sidecar...");
        let _ = child.kill();
        let _ = child.wait();
        eprintln!("[Sentinel] Sidecar stopped");
    }
}

pub fn run() {
    let session_token = if cfg!(debug_assertions) {
        std::env::var("SENTINEL_DEV_SESSION_TOKEN").unwrap_or_else(|_| generate_session_token())
    } else {
        generate_session_token()
    };
    tauri::Builder::default()
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(SidecarProcess(Mutex::new(None)))
        .manage(SidecarSessionToken(session_token))
        .manage(ActiveStreams(Mutex::new(HashMap::new())))
        .invoke_handler(tauri::generate_handler![
            get_sidecar_port,
            get_sidecar_session_token,
            sidecar_request,
            sidecar_stream,
            cancel_sidecar_stream,
        ])
        .setup(|app| {
            let token = app.state::<SidecarSessionToken>().0.clone();
            start_sidecar(app.handle(), &token);
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if let tauri::RunEvent::Exit = event {
                kill_sidecar(app_handle);
            }
        });
}
