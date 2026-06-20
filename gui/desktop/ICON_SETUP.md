# App Icon Setup

## Source of truth

`src-tauri/icons/icon.png` — a single square PNG, **1024×1024 recommended** (512×512
minimum). This is the only icon file you ever edit by hand. Every other icon
(`.icns`, `.ico`, the sized PNGs, and the Windows/Android/iOS variants) is
generated from it and should be treated as build output.

## Updating the icon

1. Replace `src-tauri/icons/icon.png` with your new artwork.
2. Regenerate the full icon set with the Tauri CLI:

   ```bash
   cd gui/desktop
   npm run tauri icon src-tauri/icons/icon.png
   ```

   This regenerates **all** platform icons at once — `icon.icns`, `icon.ico`,
   `32x32.png`, `128x128.png`, `128x128@2x.png`, the Windows `Square*Logo.png`
   set, and the `android/` + `ios/` sets — exactly as the build expects.

3. Commit the regenerated files together with the new `icon.png`.

## What the macOS build actually requires

`src-tauri/tauri.conf.json` → `bundle.icon` lists the five files used for the
desktop build:

```
icons/32x32.png
icons/128x128.png
icons/128x128@2x.png
icons/icon.icns
icons/icon.ico
```

If any of these are missing the Tauri build fails. `npm run tauri icon` always
produces all five, so prefer it over generating sizes by hand.

## Rebuild to see the new icon

```bash
cd gui/desktop
rm -rf src-tauri/target      # clears the cached bundled icon
npm run tauri dev            # or: npm run tauri build
```

macOS aggressively caches Dock icons; if the old icon lingers, a logout/login
(or `killall Dock`) forces a refresh.

## Rules

- `icon.png` is the single source of truth — keep it in version control.
- Never hand-edit the generated files; rerun `tauri icon` instead.
- The `.icns` must contain multiple resolutions (16→1024). `tauri icon` and
  macOS `iconutil` both produce valid multi-resolution `.icns`; a single-size
  PNG renamed to `.icns` will look blurry in the Dock.
