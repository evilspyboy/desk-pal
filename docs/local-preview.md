# Local PC installation and live preview

The editor's **Live preview** button displays frames from the real Desk-Pal renderer. Walking, perspective, foreground masks, placement vectors, props, lighting, idle/rest behaviour and event queues use the same Python code as the Pi. The browser receives a JPEG stream at up to 10 frames per second; the renderer continues at its usual 30 FPS. This is a saved-settings preview: save changes locally before testing them.

## First launch

Use Python with Pygame installed. On Windows, for example:

```powershell
python -m pip install pygame==2.6.1
python scripts/run_local_preview.py --backup "C:\path\to\deskpal-backup.zip"
```

Get a complete backup from the Pi's **Backup / Restore → Download saved settings and content**. First launch creates `local-preview/config`, `local-preview/assets`, a copy of the current source under `local-preview/src`, and local logs. It disables source polling and stopped-feed warnings in this copied configuration. GPIO, physical screen power and shutdown are disabled in local mode. Sleep displays a black preview and waking uses the real rest transitions. No relay or external application is launched.

Open `http://127.0.0.1:7779/`. The local editor displays **Save locally** and **Live preview**. The service listens only on loopback. The Pi's editor and settings are separate. The preview includes the touchscreen UI; the Exit button stops this local renderer.

For a hidden Windows background process:

```powershell
./scripts/start_local_preview.ps1 -Python "C:\path\to\python.exe" -Backup "C:\path\to\deskpal-backup.zip"
```

On this PC, Pygame is installed in the project-owned `scratch/local_preview_deps` folder for the Python 3.11 interpreter used to run the preview. That folder is a local dependency convenience, not part of the distributable project.

## Testing

Open **Live preview**. Tap the character or popup on the image just as on the physical screen. Use simulated buttons 1–5, including sleep/wake. Choose an application/event and send an editable test JSON payload to the local event queue. These are simulated updates, not queries to real applications. Conditions, duplicate suppression and event suppression still apply: change the payload or configure those choices locally to test different reactions. The application status buttons show the last cached simulated status.

Return to the editor to change placements, scene geometry, mappings or animations. Save locally and reopen Live preview. Scene, character and integration package imports and backup/restore work against this local installation, so they can be rehearsed without replacing live Pi data.

## Relaunch and updates

### Automated installation rehearsal

Run a backup restore and source-update rehearsal in a new directory:

```powershell
python scripts/rehearse_local_install.py --backup "C:\path\to\deskpal-backup.zip" --directory scratch/fresh-install-test --port 7781
```

The directory must not already exist. The rehearsal restores the backup, verifies every content file, adds a local customization, replaces a simulated older source file, and checks that refreshing the source preserves settings and assets. It starts the real local renderer, verifies advancing frames and saved mappings, then stops it. Results, logs and a rendered frame remain in the test directory. It does not contact the Pi. This dated rehearsal tested a clean installation from a backup. A separate [generic starter rehearsal](fresh-setup.md) subsequently tested setup without a personal backup; fresh Pi hardware and producer credentials remain separate checks.

The October 3, 2026 rehearsal passed with four scenes, one character, 35 animation sequences, four application definitions and 167 content files. GPIO and physical display power remain hardware-only checks.

Later launches do not need `--backup` and preserve local settings/assets. Launching refreshes only the copied source files from this checkout. Downloaded updates can therefore be tested while retaining your local customizations. To start another clean installation, choose a new directory with `--data-dir` and provide a backup. Existing local installations are never reinitialized automatically.

Stop a foreground run with Ctrl+C. For the background Windows launcher, run `./scripts/stop_local_preview.ps1`; it checks the recorded process is the preview runner before stopping it. Logs are `local-preview/stdout.log` and `stderr.log`. The default port is 7779; override it with `--port` or `-Port`.

The local data folder and scratch files are private and ignored for Git. This preview tests the actual scene renderer and application configuration, but GPIO wiring, physical panel power, touchscreen hardware and the PC relay require their own checks.
