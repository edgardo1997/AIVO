fn main() {
    // Auto-build sidecar.exe via PyInstaller if Python is available
    let sidecar_dist = std::path::PathBuf::from(
        std::env::var("CARGO_MANIFEST_DIR").unwrap_or_default(),
    )
    .parent()
    .unwrap()
    .join("sidecar")
    .join("dist")
    .join("sidecar.exe");

    if !sidecar_dist.exists() {
        if let Some(python) = which_python() {
            println!("cargo:warning=Building sidecar.exe with PyInstaller...");
            let status = std::process::Command::new(&python)
                .args(["-m", "PyInstaller", "--clean", "sidecar.spec"])
                .current_dir(
                    std::path::PathBuf::from(std::env::var("CARGO_MANIFEST_DIR").unwrap_or_default())
                        .parent()
                        .unwrap()
                        .join("sidecar"),
                )
                .stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::null())
                .status();

            match status {
                Ok(s) if s.success() => {
                    println!("cargo:warning=sidecar.exe built successfully");
                }
                _ => {
                    println!("cargo:warning=sidecar.exe build skipped (falling back to python launcher)");
                }
            }
        } else {
            println!("cargo:warning=Python not found; sidecar.exe will not be bundled (falling back to python launcher)");
        }
    }

    tauri_build::build()
}

fn which_python() -> Option<String> {
    for candidate in &["python", "python3", "py"] {
        if std::process::Command::new(candidate)
            .arg("--version")
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()
            .is_ok()
        {
            return Some(candidate.to_string());
        }
    }
    None
}
