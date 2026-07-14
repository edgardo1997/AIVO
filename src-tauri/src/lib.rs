use rand::{rngs::OsRng, RngCore};
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;
use tauri::Manager;

struct SidecarProcess(Mutex<Option<Child>>);
struct SidecarSessionToken(String);

#[tauri::command]
fn get_sidecar_port() -> u16 {
    8765
}

#[tauri::command]
fn get_sidecar_session_token(state: tauri::State<'_, SidecarSessionToken>) -> String {
    state.0.clone()
}

fn generate_session_token() -> String {
    let mut bytes = [0_u8; 32];
    OsRng.fill_bytes(&mut bytes);
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn find_python() -> Option<&'static str> {
    for candidate in &["python", "python3", "py"] {
        if Command::new(candidate)
            .arg("--version")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .is_ok()
        {
            return Some(candidate);
        }
    }
    None
}

fn wait_for_sidecar(timeout_secs: u64, session_token: &str) -> bool {
    let deadline = std::time::Instant::now() + Duration::from_secs(timeout_secs);
    while std::time::Instant::now() < deadline {
        if let Ok(mut stream) = TcpStream::connect_timeout(
            &"127.0.0.1:8765".parse().unwrap(),
            Duration::from_millis(500),
        ) {
            let _ = stream.set_read_timeout(Some(Duration::from_millis(750)));
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
        std::thread::sleep(Duration::from_millis(300));
    }
    false
}

fn find_bundled_sidecar(app: &tauri::AppHandle) -> Option<PathBuf> {
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
    let (sidecar_exe, sidecar_dir) = if let Some(exe) = find_bundled_sidecar(app) {
        eprintln!("[Sentinel] Found bundled sidecar.exe");
        (exe.clone(), exe.parent().unwrap().to_path_buf())
    } else if let Some(dir) = find_sidecar_dir(app) {
        let dev_exe = dir.join("dist").join("sidecar.exe");
        if dev_exe.exists() {
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
                .current_dir(&dir)
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
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
    eprintln!("[Sentinel] Starting bundled sidecar.exe from {:?}", sidecar_dir);
    match Command::new(&sidecar_exe)
        .env("SENTINEL_SESSION_TOKEN", session_token)
        .current_dir(&sidecar_dir)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
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
    let session_token = generate_session_token();
    tauri::Builder::default()
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(SidecarProcess(Mutex::new(None)))
        .manage(SidecarSessionToken(session_token))
        .invoke_handler(tauri::generate_handler![
            get_sidecar_port,
            get_sidecar_session_token,
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
