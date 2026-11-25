# Optional local Piper speech

Piper runs in an isolated process, keeping its dependencies out of the display application. Enable it in **AI & Speech → Speech**. Volume and output device come from Hardware. The adapter selects installed voices, initially `en_US-lessac-low`, with a speech speed control and functional keep-loaded checkbox. No automatic microphone recording, cloud calls or spoken event announcements are enabled.

## Adding voices

### Quick workflow

1. Open **AI & Speech → Speech → Add voice**.
2. Choose **Piper voice download** and enter an ID such as `en_GB-alan-low`, or choose **Custom model files** and provide a unique name plus the ONNX/config pair.
3. Wait for **Installed**. The selector refreshes automatically; no page reload or Desk-Pal restart is needed.
4. Select the installed voice, click **Save speech settings**, then use **Speak test text**.

Voice IDs omit the `.onnx` extension. Custom names accept letters, numbers, underscores and hyphens. The custom file picker can fill the name from the selected model filename; edit it before installation if that name is already in use.

Click **Add voice** on the Speech tab. For an official voice, enter its Piper ID and click **Download voice**; the linked sample gallery helps identify voices. For a custom voice, give it a unique ID and choose both the ONNX model and matching JSON configuration, then click **Install files**. Model uploads are streamed in 1 MB chunks, limited to 256 MB, with a 1 MB configuration limit. The model/config pair must successfully synthesize a short validation phrase in an isolated Piper process before it becomes selectable. Existing installations cannot be overwritten. Failed imports/downloads clean their staging files.

After installation, choose the voice and save speech settings. Installation alone leaves the saved selection unchanged. A loaded voice is released when a different voice is saved while idle; a voice change during playback takes effect on the next request. Only the active model is retained. Multi-speaker models use their default speaker in this version.

New voices are installed in `~/.cache/deskpal/piper/<voice-id>/`; the original flat Lessac files remain supported. Voices stay separate from code updates, settings and scene packages. Custom files are not bundled into content backups: retain your own originals and respect each model's licence.

### Validation and troubleshooting

Official downloads need an internet connection and the optional Piper environment. An unknown voice ID or download failure is shown in the installation status. Custom imports need a matching Piper JSON configuration, not just an ONNX file. A failed configuration or synthesis check keeps the voice out of the selector and leaves existing voices and the saved selection intact. First playback of a different voice includes model loading; subsequent requests are faster when **Keep voice loaded** is enabled.

On 13 October, both the official Alan download and a streamed custom-model import were tested on the Pi and physically heard by the user. Switching retained voices unloaded the previous worker. The temporary custom test voice was removed; Alan remains installed alongside Lessac, with Lessac selected and the original Hardware volume/preferences restored. The additional live voice tests peaked at approximately 510 MB in the speech worker; memory varies by model and request.

Speech is normalised toward 0.35 RMS with a bounded gain and smooth peak compression, then multiplied by the saved Hardware volume. This improves average speech loudness without changing the operating system mixer; Hardware volume remains the master control, including silence at zero.

Physical feedback on 12 October: the adjusted sample was audible and a little better, but still quiet. Its saved Hardware volume was 90%; measured output RMS was 0.2549 and peak 0.8357. The RMS target is before peak compression and master volume, so final RMS need not equal 0.35. Retain this setting for now and reassess longer speech for intelligibility rather than assuming more gain will improve it.

## Linux setup

Create `~/.venv-deskpal-tts` and install `piper-tts==1.8.0`, `soundfile` and `numpy` there. Download the Lessac low ONNX voice and matching JSON configuration into `~/.cache/deskpal/piper/` using Piper's voice downloader. The expected filenames are `en_US-lessac-low.onnx` and `en_US-lessac-low.onnx.json`. Follow the [official Piper project](https://github.com/OHF-Voice/piper1-gpl) and check the voice's model card/licence before redistributing voice assets. Model weights are not bundled with Desk-Pal.

The display invokes `src/piper_synth.py` with that environment's Python. It uses the CPU with two intra-op threads, one inter-op thread and ONNX graph optimisation. It does not change the system audio default or launch another network service.

## Memory and cancellation

All output through Desk-Pal's central `SpeechOutput` triggers the active character's `talking` sequence during playback, if one exists. Future spoken briefings should use this same path to inherit speaker preferences, cancellation and the animation link. The speech loop stops when playback stops and preserves the prior activity/route. It is not phoneme-level lip sync.

No voice loads until a speech request. With **Keep voice loaded** checked, the worker remains available after synthesis; otherwise it exits before playback. Unchecking and saving while idle releases it immediately. Turning speech off or pressing Stop releases it too. A request is limited to 500 characters, generation to 60 seconds and playback to 120 seconds. Only one request is accepted at a time; WAV files are temporary and cleaned after playback/cancellation.

The Pi 4 comparison generated roughly 2.7 seconds of audio in 1.63 seconds on average at two threads. Initial model loading is slower; retaining it avoids that cost. See the [benchmark record](../../docs/kitten-tts-benchmark-2026-10-12.md), which also records the discontinued Kitten experiment.
