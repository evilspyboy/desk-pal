# Backups and code updates

Open **Backup / Restore** on the editor's bottom toolbar. Save editor changes first: downloads contain the Pi's saved configuration, not unsaved browser drafts.

**Download saved settings and content** creates a version-1 Desk-Pal ZIP package containing the room settings, application definitions/mappings, characters, animation sequences and playback/idle preferences, scene connections, geometry, foreground masks, placements/vectors, props, artwork, sprite tags and skeleton metadata. Assets are bundled separately from code. The archive includes all supported asset files, including content not currently selected.

This is a private installation backup: personal network addresses, local paths and hardware assignments remain included. Application code, logs, telemetry and external applications' OAuth tokens are excluded. Known credential fields are stripped from exported JSON; existing matching local credential fields are preserved during restore. Reconnect independently installed external applications on a new machine. This is not yet a sanitized public content package.

**Backup scope:** the ZIP includes the ordinary room configuration and legacy switch assignments, plus supported artwork and sprite/skeleton metadata. It does **not** include the separate `hardware_settings.json` (GPIO reader assignments, sensor calibration, lux/radar/audio preferences), `ai_settings.json` (speech/provider preferences), cached Piper model files, or store-monitor credentials/data. Back up those private installation files separately if they must survive moving to another machine. Do not assume a content restore recreates hardware calibration or installed voices.

## Preview and restore

Select a backup ZIP to preview it. Previewing makes no changes. The editor shows scene/character/animation/application additions, changes and removals; changed settings sections; added/replaced/unchanged files; and missing dependencies. Archives have format/version and file-integrity checks, restricted paths and a 512 MB compressed/expanded limit. Unsupported versions and missing references block restoration.

Check the explicit restore checkbox, then choose **Restore reviewed backup**. If settings or referenced files changed after the preview, preview again before restoring. Listed settings are restored and asset files are added/replaced; extra existing asset files remain. A complete pre-restore recovery ZIP is saved under the Pi's `config/backups/` directory before changes. The editor offers its download after success. Failed settings application rolls changed files and settings back.

Artwork is reloaded and transient playback is cleared after a successful restore; received telemetry and external application state are not restored or cleared. Refresh the editor afterward to load the restored configuration. Restart Desk-Pal if hardware GPIO or startup-only display settings differ, because those inputs are initialized when the process starts. Recovery archives consume storage and can be retained/downloaded or removed manually when no longer needed; no automatic deletion is performed.

## Updating Desk-Pal

1. Save and download a backup before an update.
2. Update application code while preserving the installation's `config/` and `assets/` directories. The guarded deployment scripts already preserve these; copying example configuration over them does not.
3. If using a new copy of Desk-Pal, install compatible code first, then preview and restore the backup through the editor.
4. Check restored scene connections, artwork, placements, button wiring/preferences and application source addresses. Move the independent application producers and their private credentials separately when needed.

Shareable scene, full-character and integration packages are implemented; their workflows follow below and in [Adding integrations](adding-integrations.md). Selected individual-animation/prop-only exports, backup format migrations beyond version 1, and explicit backup support for newer private hardware/AI settings remain follow-ups. Restore support does not make arbitrary future application versions compatible with old settings automatically.
# Reusable content packages

## Character and animation packages

Open **Backup / Restore → Export / import a character**. The thumbnails list configured characters and characters found in sprite tags. Export includes the character reference (if set), all tagged artwork, owned sequences, frame crops/anchors, skeleton metadata and guides, generation notes, playback defaults, idle eligibility and transitions. This is a complete character package, not a selection of individual animations. Scenes, applications, credentials and global puppet rigs are excluded.

Preview an uploaded ZIP before confirming. Keep its ID to replace that character, or choose a new ID to add a copy. Imported sprite paths and sequence IDs are isolated under the destination ID. Tags and skeleton guide files are merged with local data. The currently selected display character, scene placements and application mappings remain unchanged. Replacement is blocked if it removes existing animation roles or would overwrite another character's content. Scene restrictions are preserved and missing scene IDs are listed in the preview.

Each import saves a full recovery backup first and rolls back files, tags and settings on failure. Preview also detects edits made since review. Reload the editor after import and select the character in the Animation Grid. References and frame skeletons then remain available for exporting generation guides. Review character names and generation notes before sharing a package.

## Individual scene packages

Open **Backup / Restore → Export / import one scene**. Each saved scene has a thumbnail and export link. Save editor changes before exporting. A scene ZIP includes backgrounds (including day/night variants), floor and blocks, foreground masks, portals, placements and their vector/playback overrides, and referenced prop animations. Character artwork and animation sequences remain separate dependencies.

Choose a scene ZIP and preview it. Leave the destination ID blank to use its original ID, or enter a new ID to add a copy. The preview identifies additions/replacements, required character animations, and connections that would be removed. Missing dependencies block import. Confirm the reviewed import, then reload the editor. Imported scene artwork and prop IDs use a scene-specific namespace. Application mappings and character libraries are retained; a replacement that removes a specifically mapped placement is blocked.

Connections to other scenes are not carried into the package. Connect its entry/exit points in Scene Map after import. Existing connections remain when their portal IDs still exist. Placement guides for the source character are assigned to the currently selected character, whose animation roles must be available. A complete recovery backup is saved before import; failed imports roll back files and settings. Scene ZIPs can still contain placement names or speech text, so review those before sharing.

