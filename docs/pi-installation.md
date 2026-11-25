# Portable Raspberry Pi installation

Use Raspberry Pi OS with a working graphical desktop, Python 3.11 or newer, and the display already configured in landscape mode. Run this installer as the user who logs into that desktop. It installs a user service and desktop-login launcher, not a root graphical application. It does not change display drivers, rotation, boot configuration or existing personal deployment services.

## Preview and install

Place this project on the Pi. Preview the generated paths and service without changing anything:

```sh
python3 scripts/install_pi.py
```

To install dependencies and generic starter content:

```sh
python3 scripts/install_pi.py --apply --install-dependencies
```

The default data directory is `~/.local/share/deskpal`; choose another dedicated directory inside your home with `--data-dir`. It contains copied source, settings, assets and logs. First install uses the bundled four scenes and Adventurer animations with no applications configured. Later installs retain settings and assets and update source. An existing desktop service is stopped before files are updated; the installer does not automatically launch the new version.

Start from the active desktop session:

```sh
~/.local/share/deskpal/start-desktop.sh
```

It imports the session's display environment into the user service. On later desktop logins the autostart entry starts that same service. Open `http://YOUR-PI:7777/` to configure Desk-Pal. The display shows `http://localhost:7777` by default; set `DESKPAL_STUDIO_URL` in the user service to a hostname/IP useful from another computer.

```sh
systemctl --user status deskpal.service
journalctl --user -u deskpal.service -n 100
systemctl --user stop deskpal.service
```

The editor is accessible on the local network and has no authentication. Keep it on a trusted network; do not expose port 7777 publicly.

## Display and buttons

Use the editor to adjust the character, scenes, daylight location and application mappings. Configure BCM GPIO assignments, button count and button test mode on **Hardware → Buttons**. These reader preferences live in `hardware_settings.json`; legacy `switches` configuration still supplies system/application button roles. Match BCM numbers to your actual wiring. The bundled six-button layout retains sleep and shutdown; four application buttons are unassigned. Refer to the README hardware pinout. GPIO 0 is also the HAT identification pin, so check compatibility with attached hardware.

The desktop user needs GPIO access, typically through Raspberry Pi OS's `gpio` group. Do not run the graphical application as root to solve a permission error. A touchscreen and working desktop session are required for hardware operation; the PC preview disables these hardware controls.

Panel standby writes only the panel's `bl_power` and `brightness` files under `/sys/class/backlight`. Raspberry Pi OS permissions vary. Check the actual panel paths and grant the desktop user permission to those exact files, or configure narrow passwordless `sudo tee` entries for those paths using `sudo visudo -f /etc/sudoers.d/deskpal`. Shutdown similarly uses `sudo shutdown -h now`. The installer deliberately does not create broad sudo permissions or guess a panel driver. If your OS does not already permit these operations, configure them before expecting the sleep/shutdown buttons to work. Physical power behaviour must be checked on your display.

## Updates and removal

Download a content backup in the editor before updating. Run the installer again from newer code; it retains the installed settings and assets. Restart through the desktop launcher. External applications and relays are separate and must be installed/configured separately; use the example integration for a first event.

To remove automatic startup, stop/disable the user service and remove `~/.config/autostart/deskpal.desktop` and `~/.config/systemd/user/deskpal.service`, then run `systemctl --user daemon-reload`. Keep the data directory if you want to reinstall with the same content.

Generated service paths and explicit data-directory handling were tested locally. Installation on a fresh Raspberry Pi OS system, session startup, GPIO and panel power have **not** been verified on hardware. The portable installer has not replaced or reimaged the working personal Pi. Later features were deployed separately through its guarded personal workflow.
