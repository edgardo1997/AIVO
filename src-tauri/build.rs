use std::path::{Path, PathBuf};
use std::time::SystemTime;

fn main() {
    let manifest_dir = PathBuf::from(
        std::env::var("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR must be available"),
    );
    let sidecar_dir = manifest_dir
        .parent()
        .expect("src-tauri must have a project parent")
        .join("sidecar");

    // Cargo must notice Python changes even though they live outside src-tauri.
    println!("cargo:rerun-if-changed={}", sidecar_dir.display());

    // Development deliberately runs the Python sources directly. Building the
    // PyInstaller binary on every `tauri dev` cycle would be slow and unnecessary.
    if std::env::var("PROFILE").as_deref() != Ok("release") {
        tauri_build::build();
        return;
    }

    let sidecar_exe = sidecar_dir.join("dist").join("sidecar.exe");
    if sidecar_is_stale(&sidecar_dir, &sidecar_exe) {
        build_sidecar(&sidecar_dir);
    }

    if !sidecar_exe.is_file() {
        panic!(
            "Production build requires an up-to-date sidecar executable at {}",
            sidecar_exe.display()
        );
    }

    tauri_build::build();
}

fn sidecar_is_stale(sidecar_dir: &Path, executable: &Path) -> bool {
    let executable_modified = match executable.metadata().and_then(|meta| meta.modified()) {
        Ok(value) => value,
        Err(_) => return true,
    };

    newest_source_modified(sidecar_dir)
        .map(|source_modified| source_modified > executable_modified)
        .unwrap_or(true)
}

fn newest_source_modified(root: &Path) -> Option<SystemTime> {
    let mut newest = None;
    let entries = std::fs::read_dir(root).ok()?;

    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            let ignored = matches!(
                path.file_name().and_then(|name| name.to_str()),
                Some("dist" | "build" | "__pycache__" | ".pytest_cache" | ".ruff_cache")
            );
            if !ignored {
                newest = newest.max(newest_source_modified(&path));
            }
        } else if is_sidecar_source(&path) {
            newest = newest.max(path.metadata().ok()?.modified().ok());
        }
    }

    newest
}

fn is_sidecar_source(path: &Path) -> bool {
    matches!(
        path.extension().and_then(|extension| extension.to_str()),
        Some("py" | "toml" | "txt" | "spec" | "json")
    )
}

fn build_sidecar(sidecar_dir: &Path) {
    let python = which_python()
        .unwrap_or_else(|| panic!("Python is required to build the production sidecar executable"));
    println!("cargo:warning=Building the current sidecar sources with PyInstaller...");

    let status = std::process::Command::new(&python)
        .args(["-m", "PyInstaller", "--clean", "sidecar.spec"])
        .current_dir(sidecar_dir)
        .status()
        .unwrap_or_else(|error| panic!("Failed to start PyInstaller with {python}: {error}"));

    if !status.success() {
        panic!("PyInstaller failed; refusing to package a stale production sidecar");
    }
}

fn which_python() -> Option<String> {
    for candidate in ["python", "python3", "py"] {
        if std::process::Command::new(candidate)
            .arg("--version")
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()
            .is_ok_and(|status| status.success())
        {
            return Some(candidate.to_string());
        }
    }
    None
}
