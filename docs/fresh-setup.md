# Fresh setup without a personal backup

The bundled `examples/starter-content.zip` contains four scenes, their floor geometry and props, and the Adventurer character's animation library. It contains no personal applications, source connections or application button assignments. Application buttons begin unassigned; sleep and shutdown retain their system roles. Existing installations are not reset by the starter option.

## Run on a PC

Use Python 3.11 or newer:

```powershell
python -m pip install -r requirements-preview.txt
python scripts/run_local_preview.py --starter --data-dir local-preview
```

Open `http://127.0.0.1:7779/`, then **Live preview**. Use **Save locally** for changes. Stop with Ctrl+C. For a hidden Windows process, use `scripts/start_local_preview.ps1 -Starter`, then `scripts/stop_local_preview.ps1` to stop it. The browser view uses the actual renderer; GPIO, shutdown and physical display power are disabled on a PC.

## First settings

Set your latitude, longitude and timezone in **Day / night settings**; the starter uses Brisbane as its example. Select a scene and inspect its saved placements. Add your own characters, scenes and props in the editor as described in the README.

In **App & Action Studio**, import `examples/integration.example.json`. Save the definition, then choose a scene, animation and location for its events. Assign a hardware button if wanted. To send a simulated event to the PC installation:

```powershell
python examples/send_example.py --deskpal http://127.0.0.1:7779 --event job_finished
```

This example sender runs separately from Desk-Pal. Replace its demo values with your application's state. Importing a definition does not install or run that application. See [Adding integrations](adding-integrations.md) for real producers.

## Updates and backups

Keep the installation's `config` and `assets` directories when updating source. Relaunching the PC runner refreshes its copied code while preserving those directories. Download a backup through **Backup / Restore** before larger changes. Scene, character and integration packages can be shared separately.

The starter ZIP uses the same validated content format as backups, but is a generic bundle rather than a copy of personal application settings. Maintainers can rebuild it explicitly with `python scripts/build_starter_content.py --content-directory PATH`; inspect the resulting content before publication.

This provides a fresh **PC** setup. A [portable Pi installer/service setup](pi-installation.md) is also available, but a fresh-Pi hardware rehearsal and final publication review remain pending. Personal Pi deployment scripts are not a general installer.

The bundled starter is an earlier content snapshot, not a mirror of the latest personal Pi additions. Later talking/hello sequences and speech voices should not be assumed present until the generic starter is explicitly rebuilt and checked.

The October 3, 2026 isolated rehearsal passed: four scenes, one character, 35 sequences and 167 content files, with no applications configured. Source updates preserved settings and assets, and the real renderer advanced frames. Starter privacy/content checks and importing the example definition also passed. Both temporary installations were removed after testing; the small [results report](starter-installation-report.json) remains.
