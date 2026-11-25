# AI & Speech

Open **AI & Speech** from the editor toolbar, or visit `/ai`. This area is separate from Hardware and normal application monitoring. Hardware configures the speaker and microphone devices; this page describes agent hooks and stores preferences for future AI/speech services.

## Available now

The separate [agent MCP bridge](../integrations/agent-mcp/README.md) lets a cooperating agent report meaningful task phases. Import its integration definition through Applications and map the events there. The bridge runs on the agent host, not automatically on the Pi. Its host may use OpenAI, Gemini, Claude or a local model, provided it supports the MCP bridge. No provider credentials are needed by Desk-Pal to receive those reports.

The **Model connections** tab saves independent connection profiles for network LLMs (**Local LLM** via PC Ollama/LAN, **OpenAI**, **Gemini**, **Claude**) and the **On-Device** local model. Selecting a network profile configures its Endpoint URL and Model name; selecting **On-Device** dynamically adjusts the form to configure the local binary path (`llama-cli`) and local GGUF model path. Conversation, TTS, STT and fallback tiers have separate preferred provider selections.

Profiles are private installation settings in `config/ai_settings.json` beside the active configuration. They are excluded from Git and ordinary content backups, like hardware preferences. They do not overwrite application mappings. API keys are deliberately not collected at this stage; provider-specific authentication and safe credential handling must be implemented before enabling cloud requests.

## Next steps & Future Roadmap

- **Expanding Cactus Needle Tool Calling**: Add further on-device tools to `_get_needle_engine()` in `voice_command_router.py` to trigger in-scene prop interactions (e.g. launching mini-game scripts, toggling room lights/props), run custom companion service actions, and execute user-defined multi-step routines directly on device.
- **Provider Adapters & Capabilities**: Implement provider adapters with capability discovery, credentials, bounded connection tests and clear status. Add deliberate push-to-talk STT, cloud speech adapters, quiet hours and optional spoken briefings/attention messages. Local test speech already has voice selection and cancellation. Local services may run on a separate computer to reduce Pi load. Evaluate suitable transcription backends on the target hardware. Automatic agent lifecycle hooks and conversational agent mode are still roadmap work. Normal application events, pending attention and hardware buttons retain their existing behaviour.

## Local Piper

The Speech tab enables local Piper with an installed-voice selector, adjustable speed, test text, progress/metrics and Stop. Lessac US English low is the initial voice. Speaker output and volume follow Hardware. Two CPU threads gave the best result on the Pi 4 benchmark.

Use **Add voice** to download an official Piper voice by its ID (with a link to voice samples), or install a custom `.onnx` model and its matching `.onnx.json` configuration. Give custom voices a unique name. Downloads show installation status, and file imports stream to disk rather than loading the model into the display process. The pair is checked with Piper before it appears in the selector; failed imports are removed and existing voices cannot be overwritten. After installation, select the voice and click **Save speech settings**. Installing does not change the currently saved voice. Multi-speaker models currently use their default speaker.

Voices are installation assets under `~/.cache/deskpal/piper/`, independent of scene/animation content and code updates. They are not included in ordinary content backups. Keep copies of custom voice files and check individual voice licences before redistribution. Switching a retained voice releases the old model; an in-progress utterance finishes before the changed selection is used for the next request.

Live validation on 13 October installed Alan low through the downloader, imported a temporary custom model/config pair through the streaming upload endpoints, and played both through the selected USB speaker. the user confirmed hearing both. Switching the retained custom voice to Alan released the first model. The temporary import was removed after testing, and the original Lessac selection, retention preference and Hardware settings were restored; Alan remains available in the installed list.

The installed list refreshes automatically after adding a voice. Save the selected voice before testing it; no restart is required. The [Piper guide](../integrations/piper-tts/README.md#quick-workflow) includes example IDs, file limits and installation troubleshooting. Additional voice tests peaked around 510 MB in the speech worker, so the earlier 447 MB measurement should not be treated as a fixed memory requirement for every voice.

**Keep voice loaded between requests** is functional: after first use, Piper remains in an isolated worker when checked. Unchecked, it releases the worker after synthesis. Unchecking and saving while idle unloads it immediately; during a request, it unloads when that request completes. Turning speech off or pressing Stop also unloads it. When speech is never used, no worker loads regardless of this checkbox. First use takes longer than subsequent requests.

Existing Kitten preferences migrate to Piper while preserving enable/retention settings and independent provider profiles. Kitten is no longer a selectable backend. Test speech does not automatically read application events or morning briefings. See [Piper setup](../integrations/piper-tts/README.md).

## Local Voice Recognition & Sentry (STT)

The Voice Recognition section in `/ai` provides an ambient speech sentry powered by `faster-whisper` (`tiny.en` quantized with int8 on CPU) and ALSA USB microphone capture (`plughw:Device,0`).

1. **Trigger Modes**:
   - **Push-to-Talk via Sprite Poking (`poke_sprite`)**: Tapping or clicking the character sprite initiates listening mode. A visual retro thought bubble appears with a pulsing red recording dot above the sprite's head. Tapping again finishes listening immediately.
   - **Wake Keyword (`wake_word`)**: Optional phrase matching (e.g., `"hey pal"`). To optimize CPU performance and eliminate spurious transcriptions from ambient TV or background room conversation:
     - **Radar Presence Gating**: Wake word transcription is automatically gated by mmWave radar presence (`radar_nearby_present`). When no one is present at the desk, Whisper inference is completely paused.
     - **Adaptive Ambient Noise Floor Tracking**: Tracks room audio levels using an exponential moving average (`ambient_floor`). Incoming volume must exceed both a calibrated base threshold (`peak > 4500`) and a delta above background sound (`effective_threshold = max(4500, ambient_floor + 1500)`). Background television audio (typically peaking around 2400–3000) is filtered out in hardware buffers with zero CPU overhead.
     - **Miss Cooldown (2.5s)**: If an ambient audio burst exceeds the energy gate but does not contain the wake word, a 2.5-second cooldown pauses wake processing, preventing continuous CPU loops on loud television scenes.
     - **Strict Compound Wake Phrases**: Wake detection enforces compound phrases (`"hey pal"`, `"hey deskpal"`, `"ok pal"`). Loose single-word variants (such as `"pal"`, `"paul"`, or `"pile"`) are rejected to avoid false activations from common conversational dialogue.
     - **Single-Breath Inline Commands**: Commands spoken in the same breath as the wake phrase (e.g., `"Hey pal, what's the weather?"`) are parsed and dispatched immediately. Execution is strictly isolated to the matched wake event and does not persist across subsequent ambient sound frames.
2. **Auto-Stop Silence Break (`2.0s`)**:
   - Monitored at 100ms intervals using the peak energy gate.
   - Once speech is detected, the sentry automatically cuts off listening after **2.0 seconds** of silence. This ensures pauses between sentences are not prematurely cut short.
3. **Always Loaded in Memory (`keep_loaded`)**:
   - Both Piper TTS and faster-whisper STT provide an independent **"Keep in memory"** toggle.
   - Piper TTS uses ~180–220 MB RAM; faster-whisper `tiny.en` uses ~120–150 MB RAM.
   - When both models remain resident in memory (~320 MB total), the Pi 4 maintains >2.4 GB free RAM, allowing near-instant speech synthesis and transcription without cold-start model load delays.
4. **Backup & Export Preservation**:
   - Full system exports via `/api/backups/download` bundle both `config/ai_settings.json` and `config/hardware_settings.json` (with API keys and secrets automatically stripped).

### On-Device Intent & Tool Calling: Cactus Needle (Operational)

Desk-Pal routes voice commands through an intelligent, self-contained **3-tier cascade** that combines microsecond exact matches, on-device structured tool calling, and fallback conversational chatting:

1. **Tier 1 — Instant Matcher (<1ms)**:
   - Direct regex and phrase matching for rapid core controls (sleep, wake, sit down, wander, current time, repeat last speech, and direct app triggers).
2. **Tier 2 — Cactus Needle On-Device Tool Caller (~111 MB RAM, ~2.5s on Pi 4 CPU)**:
   - Powered by `cactus-needle` (`3.2.7`) running natively on the Raspberry Pi 4 ARM64 CPU.
   - Evaluates natural language commands into typed Python tool calls with structured kwargs:
     - `switch_scene(scene_name)`: Dynamically searches available room scenes and schedules travel/transition.
     - `check_fuel_price(fuel_type)`: Retrieves latest fuel tracker prices and surfaces feedback card.
     - `check_weather()`: Queries weather forecast and displays the weather popup card.
     - `check_flight_deals(destination)`: Queries travel radar for flight anomalies and holiday deals.
     - `check_store_sales()`: Checks store monitor for recent sales, revenue, and customer orders.
     - `check_bmcbf_updates()`: Checks pop culture updates, games, movies, and promotions.
     - `go_to_sleep()` / `wake_up()`: Toggles standby mode and display power.
     - `sit_down()` / `wander_around()`: Directs companion to sit on chairs/rugs or explore freely.
     - `tell_current_time()` / `repeat_last_phrase()`: Real-time clock and audio memory replay.
     - `open_tv_viewer()`: Opens interactive television viewer prop in the current room.
   - **Confidence Gating (`>= 0.35`)**: Evaluates model confidence score. Intentional command queries achieve `0.52–0.90` confidence, whereas ungrounded or open-ended banter queries drop to `<0.25` and cleanly return no tool call.
   - **Stateless Execution**: Configured with `stateless=True` to prevent past conversation context leakage across independent voice commands.
3. **Tier 3 — Conversational Fallback Tiers**:
   - When Cactus Needle determines no action tool is requested (e.g. open-ended banter, creative storytelling, general queries), voice dispatch falls back through two independent tiers:
     - **Primary Chat Fallback**: Configurable to `Local LLM (LAN llama.cpp / Ollama)`, `On-Device`, `OpenAI`, `Gemini`, `Claude`, or `None (Disabled)`.
     - **Secondary Chat Fallback**: Automatic safety net if the primary tier is unreachable or fails (e.g. if the LAN LLM server is offline, it fails over to the on-device model).
   - Network providers query OpenAI-compatible `/v1/chat/completions` endpoints with persona-prompted spoken replies (non-Ollama `local` endpoints such as `llama.cpp` / `LlamaApp` automatically send `"chat_template_kwargs": {"enable_thinking": false}` and trigger a background `POST /models/unload` after replies to free shared VRAM); On-Device executes the configured local binary and model directly on the Pi. Both tiers can be configured in `/ai` under **Model connections**.

### Whistle STT (Cactus Compute)

Alongside Needle tool calling, [Cactus Compute's Whistle](https://cactuscompute.com/blog/whistle) is supported in `stt_worker.py`:
- **Ultra-compact 16.9 MB Model**: Operates with minimal memory footprint on the Pi 4.
- **Embedded C++ Audio Pipeline**: 48kHz to 16kHz resampling with `soxr` ensures clean ingestion from USB microphones.
- **Selectable in `/ai` Studio**: Can be selected as the primary STT model alongside `faster-whisper` (`tiny.en` / `base.en`).

## Playback validation and current limits

Live Pi 4 tests on 12 October confirmed cold and warm requests, retained-worker reuse, unloading when retention is disabled, and cancellation. A short cold request took about 12 seconds including voice loading; a different short warm request took 0.9 seconds. The production worker peaked at approximately 447 MB, including waveform processing. These are TTS timings, not a complete STT/LLM conversation benchmark.

Speech is normalised and its peaks smoothly compressed before the saved Hardware volume is applied. It does not change the operating system mixer. The louder sample used the actual saved 90% setting, with output peaks below the limiter ceiling. the user heard a small improvement but still described it as quiet. Treat audibility as confirmed, not a claim of loud or fully validated conversational playback. Revisit intelligibility and comfortable loudness with longer spoken briefings; do not automatically increase the user's master volume.

Kitten runtime/model files were removed from the Pi and the isolated desktop test installation was cleaned up. Historical timing records and audio samples remain for comparison.

## Talking animation

The active character's `talking` sequence plays while the central `SpeechOutput` reports audio playback. This applies to the current test button and future callers using that same TTS path; generation/loading does not animate speech. The character faces the screen at its current position, and its existing route/action clocks pause until playback ends, is stopped or fails. Popups may cover the character without removing this linkage. Sleeping/edit mode and characters without a talking sequence do not receive a visual override. This is a speaking loop, not phoneme-level lip sync.

Adventurer v1 has four larger-mouth frames, with skeleton guides and reference-generation instructions available through Animation Grid exports. A separate same-hand `wave_hello` sequence is used for return greetings and morning greetings. The original two-handed `wave_arms` remains for attention. Recorded waves on 13 October at 13:55:54 and 14:18:57 Brisbane time were `person_returned` events, not application alerts; they had no alert popup. Radar reacquisition may produce this greeting even if a user never actually left.

The first physical talking test showed sideways movement despite a common foot baseline. Reviewed per-frame anchors now compensate for 2–4 pixels of generated torso drift without changing placement coordinates. The corrected sample played successfully, and the user confirmed it looked better on 13 October. This confirms improvement, not pixel-identical artwork across frames. Source sheets, installed frames, skeletons, generation prompts and alignment notes are retained in [speech sprite assets](../assets/characters/adventurer/speech_v1/README.md).
