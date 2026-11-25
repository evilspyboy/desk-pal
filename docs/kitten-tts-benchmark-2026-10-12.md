# KittenTTS 2: first Pi 4 benchmark

> Historical snapshot: observations and test results apply to the date in this report. They do not define current settings or remaining work. See [documentation index](index.md) and [active backlog](BACKLOG.md).


Historical experiment: Kitten was subsequently removed from Desk-Pal and the Pi; Piper is now the supported local speech backend. The earlier configuration and installation descriptions below record the state at the time of that experiment.

Tested on the personal 4 GB Pi 4, aarch64 Python 3.13.5, alongside the running Desk-Pal display. Runtime: official KittenTTS 2 C++ fork commit `1ce0bb504e5452795b52ca9a3c3950e982d82bb1`. Model revision: `f2eee74f4467855ad58fe16f1fb7b7df473263fd`; compact ternary GGUF and `student_w4` decoder. Two CPU threads; on-demand process loading.

Text: “Good morning. This is the new Kitten voice.” Voice: Jasper.

| Mode | Result |
| --- | --- |
| Default reference-conditioned generation | Stopped at the 170-second application timeout; no complete WAV |
| Speaker-only conditioning (`--no-reference`) | Valid 2.64-second WAV generated in 102.68 seconds, including loading |
| Peak resident memory, successful run | 1,686.9 MiB; sampled kernel high-water mark |
| Playback | Heard through the saved USB output, but quiet; a louder limited replay was heard |
| Unloading | Confirmed no synthesis process remained after generation/playback |
| Stop control | Live API test cancelled generation and left no subprocesses or temporary speech directories |

The compact new model fits this Pi's memory; these timings are too slow for immediate conversational speech. They do not establish desktop or GPU performance. Speaker-only conditioning is the supported native faster mode and is not a full-reference quality benchmark. Speech level normalisation was added after the quiet first audition. The builder reported that the louder replay was audible but still somewhat quiet; subjective voice quality remains to be evaluated with better playback.

The Speech tab exposes the new model and an optional legacy nano fallback. Nano has not yet been benchmarked in this installation. Local test speech is enabled on the personal Pi; generic defaults remain disabled. No automatic briefing/event speech or STT is enabled. A keep-loaded preference is stored but remains inactive with the current batch backend; it should not be confused with a working persistent server.

## Piper comparison

Read-only inspection of the separate BMCBF Voice Sentry implementation found direct Piper/ONNX synthesis, cached loaded voices, bounded CPU threads, sentence queuing and cached greetings. Its selected voice is a custom BMO model; Lessac low is the fallback. This is an optimised use of Piper rather than evidence of a separate faster Piper fork. No BMCBF files were changed.

On the same Pi, `piper-tts` 1.8.0 with `en_US-lessac-low.onnx`, two intra-op threads, one inter-op thread and full ONNX graph optimisation generated the same sentence in 1.505, 1.357 and 1.378 seconds. Audio lengths were 2.528–2.656 seconds; peak memory was approximately 229.5 MB. Initial startup took 22.173 seconds, including imports and construction of both the default and replacement optimised sessions; this is not a pure model-load measurement. Warm synthesis is faster than playback and makes persistent loading and sentence chunks a promising conversational option. Kitten's measurement includes loading, so the timings are not a strictly matched warm benchmark.

Piper was installed in the optional isolated speech environment for this benchmark. It is not yet offered in Desk-Pal's Speech selector.

Subsequent deployment replaced Kitten with Piper in the Speech selector and added working process retention. Live API tests measured a cold request at 12.226 seconds (10.961 seconds loading), a warm request at 0.917 seconds with no loading, and on-demand speech at 11.560 seconds followed by unloading. These use different short test sentences. Peak worker memory with waveform normalisation was approximately 447 MB. Retention, settings-triggered unload and cancellation passed; test preferences were restored and temporary WAV directories were cleaned.

A follow-up matching BMCBF's TTS-stage timing (text to closed playable WAV) compared three runs each at one, two and four CPU threads. Mean synthesis times were 2.247, 1.625 and 2.215 seconds respectively for 2.64–2.688 seconds of audio. Two threads were fastest on this Pi. Imports took 0.644 seconds; default voice loading took 11.270 seconds, and each replacement optimised session took about 11.3 seconds. Peak memory across all session replacements was 276.3 MB. These measurements exclude STT, LLM and audio-device latency. The temporary WAV directory was automatically removed and the benchmark process exited. Raw results are retained locally in `scratch/piper_pi_quick_benchmark.json`.

A follow-up matching BMCBF's TTS-stage timing (text to closed playable WAV) compared three runs each at one, two and four CPU threads. Mean synthesis times were 2.247, 1.625 and 2.215 seconds respectively for 2.64–2.688 seconds of audio. Two threads were fastest on this Pi. Imports took 0.644 seconds; default voice loading took 11.270 seconds, and each replacement optimised session took about 11.3 seconds. Peak memory across all session replacements was 276.3 MB. These measurements exclude STT, LLM and audio-device latency. The temporary WAV directory was automatically removed and the benchmark process exited. Raw results are retained locally in `scratch/piper_pi_quick_benchmark.json`.

## Desktop CPU check

The isolated Windows test of KittenTTS 2 packed weights with its default reference-conditioned decoder completed: 187.88 seconds to load (including first downloads), then 199.98 seconds to generate 3.2 seconds of speech, with approximately 6,308.6 MB peak working set. Four CPU threads were used; no GPU. This uses a different decoder/conditioning path from the Pi test and is not a direct hardware comparison. The test process exited after saving its sample and metrics.
