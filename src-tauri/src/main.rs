#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde_json::{json, Value};
use std::{
    fs::{self, OpenOptions},
    io::{BufRead, BufReader, Write},
    path::{Path, PathBuf},
    process::{Child, ChildStdin, Command, Stdio},
    sync::Mutex,
};
use tauri::{Emitter, Manager};

struct RunningWorker {
    child: Child,
    stdin: ChildStdin,
}

#[derive(Default)]
struct WorkerHost(Mutex<Option<RunningWorker>>);

fn worker_command(app: &tauri::AppHandle, data: &Path) -> Result<Command, String> {
    let mut command;
    if cfg!(debug_assertions) {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..");
        let python = std::env::var_os("ERASE_IT_PYTHON")
            .map(PathBuf::from)
            .unwrap_or_else(|| {
                root.join(if cfg!(windows) {
                    ".venv/Scripts/python.exe"
                } else {
                    ".venv/bin/python"
                })
            });
        if !python.is_file() {
            return Err("Processing runtime is missing. Run scripts/setup-worker.py first.".into());
        }
        command = Command::new(python);
        command.arg("-m").arg("erase_it").current_dir(root);
    } else {
        let resources = app.path().resource_dir().map_err(|e| e.to_string())?;
        let default_worker = resources.join("worker/erase-it-worker.exe");
        // GPU packs are installed explicitly under app data. Validate their pinned checksum
        // manifest in install-nvidia.ps1 before atomically publishing this directory.
        let gpu_worker = data.join("runtimes/nvidia/erase-it-worker.exe");
        let matching_pack = fs::read(data.join("runtimes/nvidia/runtime-manifest.json"))
            .ok()
            .and_then(|bytes| serde_json::from_slice::<Value>(&bytes).ok())
            .is_some_and(|manifest| {
                manifest["app_version"] == env!("CARGO_PKG_VERSION")
                    && manifest["platform"] == "windows-x64"
            });
        let worker = if gpu_worker.is_file() && matching_pack {
            gpu_worker
        } else {
            default_worker
        };
        if !worker.is_file() {
            return Err("The bundled processing runtime is missing. Reinstall erase-it.".into());
        }
        command = Command::new(worker);
        command.env("ERASE_IT_FFMPEG", resources.join("media/ffmpeg.exe"));
        command.env("ERASE_IT_FFPROBE", resources.join("media/ffprobe.exe"));
    }
    command
        .arg("--data-dir")
        .arg(data)
        .env("PYTHONUNBUFFERED", "1");
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000); // CREATE_NO_WINDOW
    }
    Ok(command)
}

fn start_worker(app: &tauri::AppHandle) -> Result<RunningWorker, String> {
    let data = app.path().app_data_dir().map_err(|e| e.to_string())?;
    fs::create_dir_all(&data).map_err(|e| e.to_string())?;
    // The webview may read only app-owned previews, never arbitrary user paths.
    app.asset_protocol_scope()
        .allow_directory(&data, true)
        .map_err(|e| e.to_string())?;
    let log_path = data.join("worker.log");
    if fs::metadata(&log_path)
        .map(|m| m.len() > 1_048_576)
        .unwrap_or(false)
    {
        let _ = fs::rename(&log_path, data.join("worker.previous.log"));
    }
    let log = OpenOptions::new()
        .create(true)
        .append(true)
        .open(log_path)
        .map_err(|e| e.to_string())?;
    let mut child = worker_command(app, &data)?
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::from(log))
        .spawn()
        .map_err(|e| format!("Could not start processing runtime: {e}"))?;
    let stdin = child.stdin.take().ok_or("Worker input unavailable")?;
    let stdout = child.stdout.take().ok_or("Worker output unavailable")?;
    let handle = app.clone();
    std::thread::spawn(move || {
        for line in BufReader::new(stdout).lines() {
            match line {
                Ok(line) => match serde_json::from_str::<Value>(&line) {
                    Ok(message) => {
                        let _ = handle.emit("worker-message", message);
                    }
                    Err(_) => {
                        let _ = handle.emit("worker-message", json!({"v": 1, "event": "worker-error", "message": "The processing runtime returned invalid data. Reopen your project."}));
                    }
                },
                Err(_) => break,
            }
        }
        let _ = handle.emit("worker-message", json!({"v": 1, "event": "worker-error", "message": "The processing runtime stopped. Reopen your saved project to restart it."}));
    });
    Ok(RunningWorker { child, stdin })
}

#[tauri::command]
fn worker_request(
    app: tauri::AppHandle,
    host: tauri::State<WorkerHost>,
    request: Value,
) -> Result<(), String> {
    let text = serde_json::to_string(&request).map_err(|e| e.to_string())?;
    if text.len() > 1_048_576 || request.get("v").and_then(Value::as_i64) != Some(1) {
        return Err("Invalid worker request".into());
    }
    let mut guard = host.0.lock().map_err(|_| "Worker lock unavailable")?;
    let needs_start = match guard.as_mut() {
        Some(worker) => worker
            .child
            .try_wait()
            .map_err(|e| e.to_string())?
            .is_some(),
        None => true,
    };
    if needs_start {
        *guard = Some(start_worker(&app)?);
    }
    let worker = guard.as_mut().ok_or("Worker unavailable")?;
    writeln!(worker.stdin, "{text}")
        .and_then(|_| worker.stdin.flush())
        .map_err(|e| e.to_string())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(WorkerHost::default())
        .invoke_handler(tauri::generate_handler![worker_request])
        .build(tauri::generate_context!())
        .expect("Could not start erase-it")
        .run(|app, event| {
            if matches!(event, tauri::RunEvent::Exit) {
                if let Ok(mut worker) = app.state::<WorkerHost>().0.lock() {
                    if let Some(mut running) = worker.take() {
                        // Closing stdin asks the worker to cancel FFmpeg before it exits.
                        drop(running.stdin);
                        for _ in 0..20 {
                            if running.child.try_wait().ok().flatten().is_some() {
                                return;
                            }
                            std::thread::sleep(std::time::Duration::from_millis(50));
                        }
                        let _ = running.child.kill();
                        let _ = running.child.wait();
                    }
                }
            }
        });
}
