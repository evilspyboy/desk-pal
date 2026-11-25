# Build an application interface for Desk-Pal

These examples generalize BMCBF's separate application/relay design without requiring its source, accounts, task names or personal settings.

## Three different files and roles

| Example | Purpose |
| --- | --- |
| [Integration definition](../examples/integration.example.json) | Import into App & Action Studio. Declares the application and event names/fields so the user can map them to scenes, gestures and buttons. This does not install or start the producer. |
| [Cached status response](../examples/status.example.json) | Example JSON from the producer's read-only status endpoint, or a heartbeat pushed to Desk-Pal. Includes concise physical-button text and dated structured results. |
| [Completed job event](../examples/job-finished.example.json) | One actual occurrence, sent when work finishes. Its stable run identity prevents replaying the same result on every poll. |
| [Sender](../examples/send_example.py) | Dependency-free Python HTTP client for delivering real status/events. |

All supplied payloads are marked `demo: true`. Dates, counts and titles are examples; replace them with actual results. Desk-Pal does not launch these examples automatically.

## Producer-side interface

An application may expose `GET /api/v1/status` returning its cached snapshot. The URL/path is configurable; this is a recommended convention, not an endpoint Desk-Pal creates in your application. A separate relay can read it, or the application can push the snapshot to Desk-Pal's `/api/v1/heartbeat` directly.

Update the snapshot when real work completes. A status request must read cached state, not run scrapers, query mail, post to social media or generate summaries. Persist results where another process can read them reliably. BMCBF's web process retained old in-memory data while its scheduler produced new results: one authoritative snapshot shared across processes avoids that failure.

Use `summary` for ordinary application status and optional `button_summary` for a short useful inspection response. Normal physical buttons use the latest heartbeat's cached button text. Structured `results` fields in this example are **producer-defined**, not a built-in daily-results schema; Desk-Pal records fields for mapping conditions but does not automatically turn arbitrary fields into prose. Your application/adapter formats that prose.

Separate transport freshness (`generated_at`, heartbeat receipt time) from actual result freshness (`last_successful_check`, `completed_at`). A fresh heartbeat must not make yesterday's result appear to be today's work. State the reporting timezone and distinguish unknown/failed checks from verified zero results. Historical staging files should carry their last successful update date, not imply that a scraper ran today.

## Deliver real data

After importing the example definition, adapt the files with your actual application ID and results, then send them:

```text
python examples/send_example.py --deskpal http://YOUR-DESKPAL:7777 --app-id example_app --payload examples/status.example.json
python examples/send_example.py --deskpal http://YOUR-DESKPAL:7777 --app-id example_app --event job_finished --payload examples/job-finished.example.json
```

These exact commands send **demo data**; use copies populated from your application for real monitoring. Select **PC relay polls a JSON source** to poll an endpoint instead, with `adapter: json`, `summary_field: summary`, your `source_url` and a suitable interval. The generic relay forwards the status fields, including `button_summary`. A richer adapter is needed if your producer's schema differs or if separate named events must be discovered from its history.

Do not resend a completed job as a new occurrence on every status poll. Include a stable run/result ID and persist delivery/deduplication history across restarts. A later genuine run gets a new ID even if it returns the same counts. Queueing, duplicate suppression, attention acknowledgement and physical-button behaviour are described in [Adding integrations](adding-integrations.md).

Keep scene names, gestures, GPIO assignments, credentials and the Pi address out of the producer's results contract. Store credentials separately, use bounded requests, and handle delivery failure without disrupting the application. An importer accepts configuration data, not executable producer code.

For the current personal BMCBF adapter's exact sources and remaining limits, see [BMCBF interface notes](bmcbf-interface-notes.md).
