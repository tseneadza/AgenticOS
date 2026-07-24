// Agentic OS desktop shell.
//
// Sidecar lifecycle (FR-20): on launch, if nothing is serving :5130 we
// spawn the FastAPI sidecar from the AgenticOS venv; on exit we kill it.
// If :5130 is already alive we leave it alone and only kill what we spawned.
//
// Hub lifecycle: on launch, if the Codehome Hub is not serving :8085 we
// spawn ~/Codehome/hub/hub_server; on exit we kill what we spawned.
//
// Menu bar: native macOS app menu with View navigation, Agent quick-actions,
// and standard Window/File items. View items communicate with the React
// frontend via window.__agenticOsSetView (injected by App.jsx).

use std::net::TcpStream;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::Duration;
use tauri::menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem, Submenu};

struct SidecarState(Mutex<Option<Child>>);

struct HubState(Mutex<Option<Child>>);

fn port_alive(port: u16) -> bool {
    TcpStream::connect_timeout(
        &format!("127.0.0.1:{port}").parse().unwrap(),
        Duration::from_millis(400),
    )
    .is_ok()
}

fn sidecar_alive() -> bool {
    port_alive(5130)
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

fn hub_alive() -> bool {
    port_alive(8085)
}

fn spawn_hub() -> Option<Child> {
    let home = std::env::var("HOME").ok()?;
    let hub_bin = format!("{home}/Codehome/hub/hub_server");

    // Check if Hub binary exists before attempting to spawn
    if !std::path::Path::new(&hub_bin).exists() {
        eprintln!("[HUB] Binary not found at {hub_bin}");
        eprintln!("[HUB] Hub is optional. The app will work with just the sidecar.");
        eprintln!("[HUB] To enable Hub features, clone/build: https://github.com/Codehome/hub");
        return None;
    }

    let hub_dir = format!("{home}/Codehome/hub");
    let log_dir = format!("{home}/Codehome/hub");
    let log = std::fs::File::create(format!("{log_dir}/hub.log")).ok()?;
    let err = log.try_clone().ok()?;

    eprintln!("[HUB] Spawning hub_server from {hub_bin}...");
    match Command::new(&hub_bin)
        .current_dir(&hub_dir)
        .stdout(log)
        .stderr(err)
        .spawn()
    {
        Ok(child) => {
            eprintln!("[HUB] Spawned successfully (PID: {:?})", child.id());
            Some(child)
        }
        Err(e) => {
            eprintln!("[HUB] Failed to spawn: {e}");
            None
        }
    }
}

fn kill_hub(state: &HubState) {
    if let Ok(mut guard) = state.0.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
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

    // ---- Edit ----
    // On macOS the standard editing shortcuts (Cmd+X/C/V/A, undo/redo) are
    // delivered to the focused webview control via the app's Edit-menu items
    // carrying the predefined edit *roles*. Without this submenu, paste (and the
    // others) silently do nothing inside text inputs — e.g. the Agent prompt box.
    let undo       = PredefinedMenuItem::undo(app, None)?;
    let redo       = PredefinedMenuItem::redo(app, None)?;
    let sep_edit   = PredefinedMenuItem::separator(app)?;
    let cut        = PredefinedMenuItem::cut(app, None)?;
    let copy       = PredefinedMenuItem::copy(app, None)?;
    let paste      = PredefinedMenuItem::paste(app, None)?;
    let select_all = PredefinedMenuItem::select_all(app, None)?;
    let edit_menu = Submenu::with_items(
        app, "Edit", true,
        &[&undo, &redo, &sep_edit, &cut, &copy, &paste, &select_all],
    )?;

    // ---- View ----
    // Mirrors the JS dashboard registry (VIEWS in App.jsx). Each id is
    // "view-<registry id>"; the menu handler derives the view id generically,
    // so adding a dashboard here only needs a matching registry entry.
    let v_sysops    = MenuItem::with_id(app, "view-sysops",     "SysOps",            true, Some("cmd+1"))?;
    let v_workflows = MenuItem::with_id(app, "view-workflows",  "Workflows",         true, Some("cmd+2"))?;
    let v_webnews   = MenuItem::with_id(app, "view-web-news",   "Web News",          true, Some("cmd+3"))?;
    let v_scripts   = MenuItem::with_id(app, "view-scripts",    "Scripts",           true, Some("cmd+4"))?;
    let v_zsh       = MenuItem::with_id(app, "view-zsh-config", "Zsh Config Editor", true, Some("cmd+5"))?;
    let v_brain     = MenuItem::with_id(app, "view-brain-scanner", "Brain Scanner",  true, Some("cmd+6"))?; // Phase 16 (was Obsidian Viewer)
    let v_agent     = MenuItem::with_id(app, "view-agent",      "Agent",             true, Some("cmd+7"))?;
    let v_projects  = MenuItem::with_id(app, "view-projects",   "Projects",          true, Some("cmd+8"))?; // Phase 13d — cmd+8 so cmd+1–7 stay stable
    let sep_view    = PredefinedMenuItem::separator(app)?;
    let v_reload    = MenuItem::with_id(app, "view-reload",     "Reload",            true, Some("cmd+r"))?;

    // ---- View ▸ Theme (FR-60) ----
    // Full-skin theme switch. Each id is "theme-<key>"; the menu handler derives
    // the key generically and calls window.__agenticOsSetTheme (App.jsx) — the
    // exact mirror of the view-<id> bridge above.
    // Keys mirror theme.js THEMES exactly (8 = 4 looks x light/dark). The old
    // 4 legacy dark-only ids ("theme-terra" etc.) still resolve via theme.js's
    // LEGACY_THEMES upgrade, but the menu now exposes every variant.
    let t_terra_d  = MenuItem::with_id(app, "theme-terracotta-dark",  "Terracotta Dark",       true, None::<&str>)?;
    let t_terra_l  = MenuItem::with_id(app, "theme-terracotta-light", "Terracotta Light",      true, None::<&str>)?;
    let t_cyber_d  = MenuItem::with_id(app, "theme-cyber-dark",       "Cyber Neon Dark",       true, None::<&str>)?;
    let t_cyber_l  = MenuItem::with_id(app, "theme-cyber-light",      "Cyber Neon Light",      true, None::<&str>)?;
    let t_future_d = MenuItem::with_id(app, "theme-future-dark",      "Bold Futuristic Dark",  true, None::<&str>)?;
    let t_future_l = MenuItem::with_id(app, "theme-future-light",     "Bold Futuristic Light", true, None::<&str>)?;
    let t_term_d   = MenuItem::with_id(app, "theme-term-dark",        "Terminal Green Dark",   true, None::<&str>)?;
    let t_term_l   = MenuItem::with_id(app, "theme-term-light",       "Terminal Green Light",  true, None::<&str>)?;
    let sep_ld1 = PredefinedMenuItem::separator(app)?;
    let sep_ld2 = PredefinedMenuItem::separator(app)?;
    let sep_ld3 = PredefinedMenuItem::separator(app)?;
    let theme_menu = Submenu::with_items(
        app, "Theme", true,
        &[&t_terra_d, &t_terra_l, &sep_ld1,
          &t_cyber_d, &t_cyber_l, &sep_ld2,
          &t_future_d, &t_future_l, &sep_ld3,
          &t_term_d, &t_term_l],
    )?;
    let sep_theme   = PredefinedMenuItem::separator(app)?;

    let view_menu = Submenu::with_items(
        app, "View", true,
        &[&v_sysops, &v_workflows, &v_webnews, &v_scripts, &v_zsh, &v_brain, &v_projects, &v_agent,
          &sep_theme, &theme_menu, &sep_view, &v_reload],
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
    let sep_hud    = PredefinedMenuItem::separator(app)?;
    let to_hud     = MenuItem::with_id(app, "window-minimize-to-hud", "Minimize to HUD", true, Some("cmd+shift+h"))?;

    let window_menu = Submenu::with_items(
        app, "Window", true,
        &[&minimize, &maximize, &sep_win, &fullscreen, &sep_hud, &to_hud],
    )?;

    Menu::with_items(app, &[&app_menu, &file_menu, &edit_menu, &view_menu, &agent_menu, &window_menu])
}

// ---- Menu-bar tray (FR-61) ----
// The OSA status item that lives in the macOS menu bar (where Docker/Ollama
// sit). A small dropdown of quick actions; events are routed by id below,
// mirroring the app-menu handler.
fn build_tray_menu(app: &tauri::App) -> tauri::Result<Menu<tauri::Wry>> {
    use tauri_plugin_autostart::ManagerExt;
    let open    = MenuItem::with_id(app, "tray-open",       "Open Agentic OS",      true, None::<&str>)?;
    let hud     = MenuItem::with_id(app, "tray-toggle-hud", "Toggle HUD",           true, None::<&str>)?;
    let sep1    = PredefinedMenuItem::separator(app)?;
    let brief   = MenuItem::with_id(app, "tray-briefing",   "Run Morning Briefing", true, None::<&str>)?;
    let restart = MenuItem::with_id(app, "tray-restart",    "Restart Sidecar",      true, None::<&str>)?;
    let sep2    = PredefinedMenuItem::separator(app)?;
    let autostart_on = app.autolaunch().is_enabled().unwrap_or(false);
    let launch  = CheckMenuItem::with_id(app, "tray-autostart", "Launch at Login", true, autostart_on, None::<&str>)?;
    let sep3    = PredefinedMenuItem::separator(app)?;
    let quit    = PredefinedMenuItem::quit(app, Some("Quit Agentic OS"))?;
    Menu::with_items(app, &[&open, &hud, &sep1, &brief, &restart, &sep2, &launch, &sep3, &quit])
}

fn on_tray_menu_event(app: &tauri::AppHandle, event: tauri::menu::MenuEvent) {
    use tauri::Manager;
    match event.id().as_ref() {
        "tray-open" => {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.show();
                let _ = w.set_focus();
            }
        }
        "tray-toggle-hud" => {
            if let Some(hud) = app.get_webview_window("hud") {
                if hud.is_visible().unwrap_or(false) {
                    let _ = hud.hide();
                } else {
                    let _ = hud.show();
                    let _ = hud.set_focus();
                }
            }
        }
        "tray-briefing" => {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.eval(
                    "fetch('http://localhost:5130/api/workflows/morning-briefing/run',{method:'POST'}).catch(()=>{})",
                );
            }
        }
        "tray-restart" => {
            let state = app.state::<SidecarState>();
            kill_sidecar(&state);
            std::thread::sleep(Duration::from_millis(600));
            let child = spawn_sidecar();
            *state.0.lock().unwrap() = child;
        }
        "tray-autostart" => {
            use tauri_plugin_autostart::ManagerExt;
            let am = app.autolaunch();
            if am.is_enabled().unwrap_or(false) {
                let _ = am.disable();
            } else {
                let _ = am.enable();
            }
        }
        _ => {}
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ))
        .manage(SidecarState(Mutex::new(None)))
        .manage(HubState(Mutex::new(None)))
        // Close-to-hide (FR-62): keep the app resident in the menu bar — closing
        // a window hides it instead of quitting. Real exit is the tray/menu Quit,
        // which triggers the RunEvent::Exit cleanup below.
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .setup(|app| {
            use tauri::Manager;

            // Build and set the native menu bar
            let menu = build_menu(app)?;
            app.set_menu(menu)?;

            // Menu-bar tray icon (FR-61) — the OSA status item.
            // Embed the icon at compile time so the tray always renders; in dev
            // builds app.default_window_icon() can be None, which would silently
            // skip the tray entirely.
            {
                use tauri::tray::TrayIconBuilder;
                let tray_menu = build_tray_menu(app)?;
                let tray_icon = app.default_window_icon().cloned();
                let builder = TrayIconBuilder::new()
                    .title("")
                    .tooltip("Agentic OS")
                    .menu(&tray_menu)
                    .show_menu_on_left_click(true)
                    .on_menu_event(on_tray_menu_event);
                let builder = if let Some(icon) = tray_icon {
                    builder.icon(icon)
                } else {
                    builder.icon(tauri::include_image!("icons/32x32.png"))
                };
                match builder.build(app) {
                    Ok(tray) => {
                        let _ = tray.set_visible(true);
                        let _ = tray.set_title(Some(""));
                    }
                    Err(e) => eprintln!("[TRAY] ERROR building tray: {e:?}"),
                }
            }

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
                    // Theme switch (FR-60) — any "theme-<key>" item drives the
                    // React bridge, same pattern as view navigation above.
                    id if id.starts_with("theme-") => {
                        let key = &id["theme-".len()..];
                        let _ = window.eval(&format!(
                            "window.__agenticOsSetTheme && window.__agenticOsSetTheme('{key}')",
                        ));
                    }
                    // Minimize to HUD (FR-63) — drop the HUD where the sidebar
                    // was (main's content top-left), float it, then hide main.
                    "window-minimize-to-hud" => {
                        if let Some(hud) = app.get_webview_window("hud") {
                            if let Ok(pos) = window.inner_position() {
                                let _ = hud.set_position(pos);
                            }
                            let _ = hud.show();
                            let _ = hud.set_focus();
                        }
                        let _ = window.hide();
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

            // Hub auto-start
            if !hub_alive() {
                let child = spawn_hub();
                if child.is_some() {
                    for _ in 0..20 {
                        if hub_alive() {
                            break;
                        }
                        std::thread::sleep(Duration::from_millis(250));
                    }
                }
                *app.state::<HubState>().0.lock().unwrap() = child;
            }

            // Launch-at-login (FR-62): default ON, first run only; afterward we
            // respect whatever the user set via the tray toggle.
            {
                use tauri_plugin_autostart::ManagerExt;
                if let Ok(home) = std::env::var("HOME") {
                    let data_dir = format!("{home}/Codehome/AgenticOS/data");
                    let marker = format!("{data_dir}/.autostart_initialized");
                    if !std::path::Path::new(&marker).exists() {
                        let _ = app.autolaunch().enable();
                        let _ = std::fs::create_dir_all(&data_dir);
                        let _ = std::fs::write(&marker, "1");
                    }
                }
            }

            // macOS Tahoe tray-icon onboarding (FR-61b): on first launch,
            // show a native dialog explaining the "Allow in Menu Bar"
            // permission and open System Settings directly.
            #[cfg(target_os = "macos")]
            {
                if let Ok(home) = std::env::var("HOME") {
                    let data_dir = format!("{home}/Codehome/AgenticOS/data");
                    let marker = format!("{data_dir}/.tray_onboarding_shown");
                    if !std::path::Path::new(&marker).exists() {
                        let _ = std::fs::create_dir_all(&data_dir);
                        let _ = std::fs::write(&marker, "1");
                        std::thread::spawn(move || {
                            std::thread::sleep(Duration::from_secs(3));
                            let script = r#"
                                set userChoice to button returned of (display dialog ¬
                                    "To see the OSA tray icon in your menu bar, enable it in System Settings." & return & return & ¬
                                    "Go to: System Settings → Menu Bar → set \"Agentic OS\" to ON" ¬
                                    with title "Agentic OS — Menu Bar Setup" ¬
                                    buttons {"Skip", "Open Settings"} ¬
                                    default button "Open Settings" ¬
                                    with icon note)
                                if userChoice is "Open Settings" then
                                    do shell script "open 'x-apple.systempreferences:com.apple.ControlCenter-Settings.extension?MenuBar'"
                                end if
                            "#;
                            let _ = Command::new("osascript")
                                .arg("-e")
                                .arg(script)
                                .output();
                        });
                    }
                }
            }

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            use tauri::Manager;
            match event {
                // When the last visible window is closed, Tauri asks to exit.
                // Prevent it so the app stays resident behind the tray icon.
                tauri::RunEvent::ExitRequested { api, .. } => {
                    api.prevent_exit();
                }
                // Real quit (tray/menu Quit) — clean up the processes we spawned.
                tauri::RunEvent::Exit => {
                    kill_hub(&app_handle.state::<HubState>());
                    kill_sidecar(&app_handle.state::<SidecarState>());
                }
                _ => {}
            }
        });
}
