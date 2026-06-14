// Agentic OS desktop shell.
//
// Sidecar lifecycle (FR-20): on launch, if nothing is serving :5130 we
// spawn the FastAPI sidecar from the AgenticOS venv; on exit we kill it.
// If :5130 is already alive we leave it alone and only kill what we spawned.
//
// Menu bar: native macOS app menu with View navigation, Agent quick-actions,
// and standard Window/File items. View items communicate with the React
// frontend via window.__agenticOsSetView (injected by App.jsx).

use std::net::TcpStream;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::Duration;
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem, Submenu};

struct SidecarState(Mutex<Option<Child>>);

fn sidecar_alive() -> bool {
    TcpStream::connect_timeout(
        &"127.0.0.1:5130".parse().unwrap(),
        Duration::from_millis(400),
    )
    .is_ok()
}

fn spawn_sidecar() -> Option<Child> {
    let home = std::env::var("HOME").ok()?;
    let root = format!("{home}/Codehome/AgenticOS");
    let python = format!("{root}/.venv/bin/python");
    let log_dir = format!("{root}/data/logs");
    std::fs::create_dir_all(&log_dir).ok();
    let log = std::fs::File::create(format!("{log_dir}/sidecar.log")).ok()?;
    let err = log.try_clone().ok()?;

    Command::new(python)
        .args(["-m", "gui.sidecar"])
        .current_dir(&root)
        .stdout(log)
        .stderr(err)
        .spawn()
        .ok()
}

fn kill_sidecar(state: &SidecarState) {
    if let Ok(mut guard) = state.0.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

fn build_menu(app: &tauri::App) -> tauri::Result<Menu<tauri::Wry>> {
    // ---- Agentic OS (app name menu) ----
    let about       = PredefinedMenuItem::about(app, None, None)?;
    let sep_app1    = PredefinedMenuItem::separator(app)?;
    let hide        = PredefinedMenuItem::hide(app, None)?;
    let hide_others = PredefinedMenuItem::hide_others(app, None)?;
    let show_all    = PredefinedMenuItem::show_all(app, None)?;
    let sep_app2    = PredefinedMenuItem::separator(app)?;
    let quit        = PredefinedMenuItem::quit(app, None)?;

    let app_menu = Submenu::with_items(
        app, "Agentic OS", true,
        &[&about, &sep_app1, &hide, &hide_others, &show_all, &sep_app2, &quit],
    )?;

    // ---- File ----
    let close_window = PredefinedMenuItem::close_window(app, None)?;
    let file_menu = Submenu::with_items(app, "File", true, &[&close_window])?;

    // ---- View ----
    // Mirrors the JS dashboard registry (VIEWS in App.jsx). Each id is
    // "view-<registry id>"; the menu handler derives the view id generically,
    // so adding a dashboard here only needs a matching registry entry.
    let v_sysops    = MenuItem::with_id(app, "view-sysops",     "SysOps",            true, Some("cmd+1"))?;
    let v_workflows = MenuItem::with_id(app, "view-workflows",  "Workflows",         true, Some("cmd+2"))?;
    let v_webnews   = MenuItem::with_id(app, "view-web-news",   "Web News",          true, Some("cmd+3"))?;
    let v_scripts   = MenuItem::with_id(app, "view-scripts",    "Scripts",           true, Some("cmd+4"))?;
    let v_zsh       = MenuItem::with_id(app, "view-zsh-config", "Zsh Config Editor", true, Some("cmd+5"))?;
    let v_obsidian  = MenuItem::with_id(app, "view-obsidian",   "Obsidian Viewer",   true, Some("cmd+6"))?;
    let v_agent     = MenuItem::with_id(app, "view-agent",      "Agent",             true, Some("cmd+7"))?;
    let sep_view    = PredefinedMenuItem::separator(app)?;
    let v_reload    = MenuItem::with_id(app, "view-reload",     "Reload",            true, Some("cmd+r"))?;

    let view_menu = Submenu::with_items(
        app, "View", true,
        &[&v_sysops, &v_workflows, &v_webnews, &v_scripts, &v_zsh, &v_obsidian, &v_agent, &sep_view, &v_reload],
    )?;

    // ---- Agent ----
    let a_briefing = MenuItem::with_id(app, "agent-morning-briefing", "Run Morning Briefing", true, None::<&str>)?;
    let sep_agent  = PredefinedMenuItem::separator(app)?;
    let a_restart  = MenuItem::with_id(app, "agent-restart-sidecar",  "Restart Sidecar",     true, None::<&str>)?;

    let agent_menu = Submenu::with_items(
        app, "Agent", true,
        &[&a_briefing, &sep_agent, &a_restart],
    )?;

    // ---- Window ----
    let minimize   = PredefinedMenuItem::minimize(app, None)?;
    let maximize   = PredefinedMenuItem::maximize(app, None)?;
    let sep_win    = PredefinedMenuItem::separator(app)?;
    let fullscreen = PredefinedMenuItem::fullscreen(app, None)?;

    let window_menu = Submenu::with_items(
        app, "Window", true,
        &[&minimize, &maximize, &sep_win, &fullscreen],
    )?;

    Menu::with_items(app, &[&app_menu, &file_menu, &view_menu, &agent_menu, &window_menu])
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(SidecarState(Mutex::new(None)))
        .setup(|app| {
            use tauri::Manager;

            // Build and set the native menu bar
            let menu = build_menu(app)?;
            app.set_menu(menu)?;

            // Handle menu events
            app.on_menu_event(|app, event| {
                let Some(window) = app.get_webview_window("main") else { return };
                match event.id().as_ref() {
                    "view-reload" => {
                        let _ = window.eval("window.location.reload()");
                    }
                    // View navigation — any "view-<id>" item maps to the matching
                    // registry id and calls the hook exposed by App.jsx (FR-51).
                    id if id.starts_with("view-") => {
                        let view = &id["view-".len()..];
                        let _ = window.eval(&format!(
                            "window.__agenticOsSetView && window.__agenticOsSetView('{view}')",
                        ));
                    }
                    // Agent quick-actions
                    "agent-morning-briefing" => {
                        let _ = window.eval(
                            "fetch('http://localhost:5130/api/workflows/morning-briefing/run',\
                             {method:'POST'}).catch(()=>{})",
                        );
                    }
                    "agent-restart-sidecar" => {
                        let state = app.state::<SidecarState>();
                        kill_sidecar(&state);
                        std::thread::sleep(Duration::from_millis(600));
                        let child = spawn_sidecar();
                        *state.0.lock().unwrap() = child;
                    }
                    _ => {}
                }
            });

            // Sidecar auto-start
            if !sidecar_alive() {
                let child = spawn_sidecar();
                if child.is_some() {
                    for _ in 0..20 {
                        if sidecar_alive() {
                            break;
                        }
                        std::thread::sleep(Duration::from_millis(250));
                    }
                }
                *app.state::<SidecarState>().0.lock().unwrap() = child;
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            use tauri::Manager;
            if let tauri::RunEvent::Exit = event {
                kill_sidecar(&app_handle.state::<SidecarState>());
            }
        });
}
