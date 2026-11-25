# Pi connectivity health

Open **Pi health**, beside **Day / night settings** above the scene, to enable monitoring, choose the interval, view its latest result and save alert behaviour. Settings live under `config.system_health` and travel with the normal private backup.

The default is enabled, every 30 seconds, **Until acknowledged**. Checks run on a background thread and do not block animation or touch input. They attempt TCP connections to port 443 at two independent public endpoints (1.1.1.1 and 8.8.8.8), with three-second connection timeouts. No store credentials, application summaries or user data are transmitted. Either endpoint succeeding is sufficient. This measures network reachability, not the health of every application, DNS or every website. Networks that deliberately block both probes can disable this check.

Three consecutive failed checks create one outage incident. Two consecutive successful checks clear it. A local route check distinguishes no usable route from failed internet probes; having a route is not proof that Wi-Fi/router service works end to end.

## Alert modes

- **Notify once:** a short waving reaction per outage; normal events then continue. The explanation remains available by tapping the character until recovery.
- **Until acknowledged:** wave until the character is tapped. Hold the original explanation popup until dismissal, then continue normal events. Do not repeat that incident after acknowledgement. A later outage is a new incident.
- **Until connection restored:** wave until tapped; after its popup is dismissed, resume the warning while the outage continues. Recovery automatically removes the matching queued/active connectivity reaction. Other application alerts and events are retained.

Checks and retries continue in every mode, including standby. Warnings queue while asleep and never wake the screen. Recovery or disabling monitoring clears only the connectivity incident; physical application buttons retain their usual behaviour. The connectivity warning is acknowledged by tapping the character; it has no assigned application button.

Outage/recovery/disable changes and queued reactions are recorded in the existing local activity history. `GET /api/system-health` provides cached status, check timestamp, route/reachability results, enabled state and selected mode. Reading status does not run another probe. Local Live preview disables real checks.

## Verification

Seven isolated tests passed locally and on the Pi: failure/recovery debounce, single-incident queue deduplication, one-time and acknowledgement modes, repeat-until-restored popup behaviour, settings validation, independent endpoints and removal of an active warning while preserving a genuine queued order. Existing attention-handler tests pass. The deployed Pi reports online and saved settings were preserved. No live network outage was induced; actual Wi-Fi/cable loss is an optional future hardware check.

Sources: `src/system_health.py`, `src/system_health_editor.js` (embedded in the editor), and the small renderer/queue hooks. Keep the embedded editor copy synchronized after changes.
