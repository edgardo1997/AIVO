use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;
use tauri::Manager;

struct SidecarProcess(Mutex<Option<Child>>);

#[tauri::command]
fn get_sidecar_port() -> u16 {
    8765
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

fn wait_for_sidecar(timeout_secs: u64) -> bool {
    let deadline = std::time::Instant::now() + Duration::from_secs(timeout_secs);
    while std::time::Instant::now() < deadline {
        if TcpStream::connect_timeout(
            &"127.0.0.1:8765".parse().unwrap(),
            Duration::from_millis(500),
        )
        .is_ok()
        {
            return true;
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

fn start_sidecar(app: &tauri::AppHandle) {
    let (sidecar_exe, sidecar_dir) = if let Some(exe) = find_bundled_sidecar(app) {
        eprintln!("[AIVO] Found bundled sidecar.exe");
        (exe.clone(), exe.parent().unwrap().to_path_buf())
    } else if let Some(dir) = find_sidecar_dir(app) {
        let dev_exe = dir.join("dist").join("sidecar.exe");
        if dev_exe.exists() {
            eprintln!("[AIVO] Found dev sidecar.exe at {:?}", dev_exe);
            (dev_exe, dir.join("dist"))
        } else {
            // Fallback: run via python
            let python = match find_python() {
                Some(p) => p,
                None => {
                    eprintln!("[AIVO] Python not found. Install Python 3.12+ or build sidecar.exe with PyInstaller.");
                    return;
                }
            };
            eprintln!("[AIVO] Starting sidecar with {} from {:?}", python, dir);
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
                .current_dir(&dir)
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .spawn()
            {
                Ok(child) => {
                    let state = app.state::<SidecarProcess>();
                    *state.0.lock().unwrap() = Some(child);
                    eprintln!("[AIVO] Sidecar process started, waiting for it to be ready...");
                    if wait_for_sidecar(15) {
                        eprintln!("[AIVO] Sidecar ready on port 8765");
                    } else {
                        eprintln!("[AIVO] Sidecar did not become ready within 15s");
                    }
                }
                Err(e) => eprintln!("[AIVO] Failed to start sidecar: {}", e),
            }
            return;
        }
    } else {
        eprintln!("[AIVO] sidecar/ directory not found. Check your installation.");
        return;
    };

    // Launch bundled sidecar.exe
    eprintln!("[AIVO] Starting bundled sidecar.exe from {:?}", sidecar_dir);
    match Command::new(&sidecar_exe)
        .current_dir(&sidecar_dir)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
    {
        Ok(child) => {
            let state = app.state::<SidecarProcess>();
            *state.0.lock().unwrap() = Some(child);
            eprintln!("[AIVO] sidecar.exe started, waiting for it to be ready...");
            if wait_for_sidecar(15) {
                eprintln!("[AIVO] sidecar.exe ready on port 8765");
            } else {
                eprintln!("[AIVO] sidecar.exe did not become ready within 15s");
            }
        }
        Err(e) => {
            eprintln!("[AIVO] Failed to start sidecar.exe: {}", e);
        }
    }
}

fn kill_sidecar(app: &tauri::AppHandle) {
    let state = app.state::<SidecarProcess>();
    let mut guard = state.0.lock().unwrap();
    if let Some(mut child) = guard.take() {
        eprintln!("[AIVO] Stopping sidecar...");
        let _ = child.kill();
        let _ = child.wait();
        eprintln!("[AIVO] Sidecar stopped");
    }
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_process::init())
        .manage(SidecarProcess(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![get_sidecar_port])
        .setup(|app| {
            start_sidecar(app.handle());
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
