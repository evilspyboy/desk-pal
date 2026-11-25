# Desk-Pal external integration contract

Current consumer guidance, reviewed 13 October 2026. The [earlier proposal](INTEGRATION_SPEC_HISTORY.md) is historical and includes superseded fixed mappings and force-check behavior.

Desk-Pal displays other applications' work. A separate producer or adapter owns polling, scraping, authentication and business logic. Add/import its definition through [Applications](adding-integrations.md); this does not install or launch the producer. Application IDs and event names are configurable, not restricted to this personal installation.

## Publishing events

Use `POST /api/v1/event` on the configured Desk-Pal address. Example milestone:

```json
{
  "app_id": "example_app",
  "event": "job_finished",
  "event_id": "example-run-42",
  "status": "healthy",
  "summary": "Finished processing 12 items",
  "items_processed": 12
}
```

Map `job_finished` to a scene/animation/location in the editor. The event does not hard-code a gesture or drop a prop automatically. Preserve a stable ID on retries; a genuine later run uses a new ID. Do not repeatedly describe an unchanged cached result as a new occurrence. See the [worked producer interface](producer-interface-example.md) for status/result contracts and test fixtures.

For cached health/status, use `POST /api/v1/heartbeat` with `app_id`, `status`, `summary` and optionally `button_summary`, `ttl_seconds` and structured result fields. `/api/v1/event` with `event: "heartbeat"` also follows the named-event ingestion path. Heartbeats refresh state even when their visual reaction is suppressed. Choose heartbeat cadence/TTL separately from slow upstream data collection.

For attention, publish a named event with `attention_needed: true` and a useful `summary`, then configure its attention mapping. `POST /api/v1/alert` is also supported and defaults to the alert event. Whether it waves until interaction depends on consumer settings. Do not assume a specific gesture, popup or physical button without configuring it.

## Buttons, queue and sleep

Normal application buttons use the latest cached heartbeat's `button_summary` or ordinary summary; they do not force a live producer check. A matching button or character tap can acknowledge waiting attention and display the original alert. Popups remain until dismissed. Named events are milestones unless explicitly configured otherwise; zero-override event loops complete one cycle by default.

Event suppression skips animations while retaining reception/logging and health. Duplicate suppression skips successive unchanged payloads. During standby, monitoring continues and the queue follows standby compaction/expiry rules; it is not a guaranteed replay of every old routine update. See [consumer controls](adding-integrations.md) and [standby](idle-and-standby.md).

## Helpers and compatibility

Start new integrations from [integration.example.json](../examples/integration.example.json) and [send_example.py](../examples/send_example.py), with the worked producer guide above. Producers should use bounded timeouts, fail independently of Desk-Pal, and retain important delivery identities/outbox state when retries are required.

The legacy [deskpal_client.py](../src/deskpal_client.py) helper exists, but has an installation-specific default host and limited fire-and-forget convenience methods. Pass an explicit host; its helpers do not guarantee delivery or define modern attention/mapping behavior. It is not a generic service installer or an instruction to use the personal Pi address. Public-file selection still needs review before distribution.

Existing BMCBF consumer assumptions and requested producer improvements are in [BMCBF interface notes](bmcbf-interface-notes.md). Do not change another application's runtime files as part of Desk-Pal work without its owner's authorization.
