"""Line-based faster-whisper STT worker process isolated from display/pygame environment."""
import json
import os
import sys
import time
import resource
from pathlib import Path

def main():
    if hasattr(os, 'nice'):
        try:
            os.nice(10)
        except Exception:
            pass

    model = None
    loaded_model_name = None
    
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            cmd = req.get("cmd", "transcribe")
            
            if cmd == "ping":
                mem_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
                print(json.dumps({
                    "status": "ready",
                    "loaded": model is not None,
                    "model": loaded_model_name,
                    "memory_mb": mem_mb
                }), flush=True)
                continue

            if cmd == "unload":
                model = None
                loaded_model_name = None
                print(json.dumps({"status": "unloaded"}), flush=True)
                break
                
            model_name = req.get("model", "tiny.en")
            threads = int(req.get("threads", 1))
            audio_path = req.get("path")
            
            started = time.monotonic()
            load_seconds = 0.0
            
            # Load model if not loaded or if model name changed
            if model is None or loaded_model_name != model_name:
                model = None
                t_load_start = time.monotonic()
                if model_name == "whistle":
                    import needle
                    model = needle.Whistle()
                else:
                    from faster_whisper import WhisperModel
                    # Run int8 quantized inference on CPU
                    model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=threads)
                load_seconds = time.monotonic() - t_load_start
                loaded_model_name = model_name
            
            if not audio_path or not os.path.exists(audio_path):
                print(json.dumps({"error": f"Audio file not found: {audio_path}"}), flush=True)
                continue
            
            import soundfile as sf
            import numpy as np
            
            audio, rate = sf.read(audio_path)
            if not len(audio) or not np.isfinite(audio).all():
                print(json.dumps({"error": "Invalid audio data in input file"}), flush=True)
                continue
                
            # If multi-channel, convert to mono
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
                
            # Convert to float32
            if audio.dtype != np.float32:
                audio = audio.astype(np.float32)
                
            duration_sec = round(len(audio) / rate, 2)
            peak = float(np.max(np.abs(audio)))
            
            # BMCBF Noise Gate: reject pure silence / ambient room hum
            if peak < 0.04:
                print(json.dumps({
                    "text": "",
                    "peak": round(peak, 3),
                    "duration": duration_sec,
                    "is_silence": True,
                    "load_seconds": round(load_seconds, 2),
                    "inference_seconds": 0.0,
                    "model": loaded_model_name
                }), flush=True)
                continue
                
            # Audio normalisation towards 0.5 peak (BMCBF strategy)
            if peak < 0.95:
                audio = audio * min(3.0, (0.5 / max(peak, 0.001)))
                
            # Transcribe
            t_infer_start = time.monotonic()
            if loaded_model_name == "whistle":
                keywords = req.get("keywords") or ["hey pal", "deskpal", "desk-pal"]
                res = model.transcribe(audio_path, language="en", keywords=keywords)
                text = (res.get("text") or "").strip()
            else:
                # Transcribe with greedy search (beam_size=1) for minimal latency
                segments, info = model.transcribe(
                    audio,
                    beam_size=1,
                    language="en",
                    condition_on_previous_text=False,
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=400)
                )
                text_parts = [seg.text for seg in segments]
                text = " ".join(text_parts).strip()
            inference_seconds = time.monotonic() - t_infer_start
            
            mem_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
            
            print(json.dumps({
                "text": text,
                "peak": round(peak, 3),
                "duration": duration_sec,
                "is_silence": len(text) == 0,
                "load_seconds": round(load_seconds, 2),
                "inference_seconds": round(inference_seconds, 2),
                "total_seconds": round(time.monotonic() - started, 2),
                "memory_mb": mem_mb,
                "model": loaded_model_name
            }), flush=True)
            
        except Exception as err:
            print(json.dumps({"error": str(err)[:400]}), flush=True)

if __name__ == "__main__":
    main()
