"""Line-based Piper worker isolated from the display's Python environment."""
import json
import sys
import time
import resource
from pathlib import Path

def main():
    voice=None;loaded_voice=None
    for line in sys.stdin:
        try:
            request=json.loads(line)
            started=time.monotonic();load_seconds=0
            if voice is None or loaded_voice != request['voice']:
                voice=None
                from piper import PiperVoice
                from piper.config import PiperConfig
                import onnxruntime as ort
                from piper_voices import resolve
                import os
                model=resolve(request['voice'])
                opts=ort.SessionOptions();opts.intra_op_num_threads=min(4, os.cpu_count() or 4);opts.inter_op_num_threads=1
                opts.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                voice=PiperVoice(config=PiperConfig.from_dict(json.loads(Path(str(model)+'.json').read_text())),
                    session=ort.InferenceSession(str(model),opts,providers=['CPUExecutionProvider']))
                load_seconds=time.monotonic()-started
                loaded_voice=request['voice']
            if request.get('action') == 'preload':
                print(json.dumps({'action':'preload','status':'loaded','load_seconds':round(load_seconds,3),
                    'voice':loaded_voice,'peak_memory_mb':round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,1)}),flush=True)
                continue
            import wave
            from piper import SynthesisConfig
            synthesis_started=time.monotonic()
            with wave.open(request['path'],'wb') as output:
                voice.synthesize_wav(request['text'],output,syn_config=SynthesisConfig(length_scale=1/request['speed']))
            import soundfile as sf
            import numpy as np
            audio,rate=sf.read(request['path'])
            if not len(audio) or not np.isfinite(audio).all():raise RuntimeError('Piper returned invalid audio')
            rms=float(np.sqrt(np.mean(np.square(audio))))
            gain=min(8,.35/rms) if rms>1e-5 else 1
            # Smoothly compress peaks before the user's master volume is applied.
            # This raises average speech loudness without hard clipping consonants.
            audio=.95*np.tanh(audio*gain/.95)*request['volume']
            sf.write(request['path'],audio,rate,format='WAV',subtype='PCM_16')
            print(json.dumps({'generation_seconds':round(time.monotonic()-started,3),
                'synthesis_seconds':round(time.monotonic()-synthesis_started,3),
                'load_seconds':round(load_seconds,3),'audio_seconds':round(len(audio)/rate,3),
                'peak_memory_mb':round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,1),
                'voice':loaded_voice,'volume':request['volume'],'output_peak':round(float(np.max(np.abs(audio))),4),
                'output_rms':round(float(np.sqrt(np.mean(np.square(audio)))),4)}),flush=True)
        except Exception as error:
            print(json.dumps({'error':str(error)[:400]}),flush=True)

if __name__=='__main__':main()
