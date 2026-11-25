"""Visual speech overlay for every request through the central TTS output."""
import time

def tick(app, now=None):
    now=time.monotonic() if now is None else now
    output=getattr(app,'speech_output',None)
    playing=output is not None and output.snapshot().get('state')=='playing'
    sequence=getattr(app,'character_sequences',{}).get('talking')
    eligible=playing and sequence and not app.is_sleeping and not app.edit_mode
    previous=getattr(app,'speech_reaction',None)
    if previous:
        elapsed=max(0,now-previous['last_tick'])
        queue=getattr(app,'activity_queue',None)
        if queue:
            for key in ('started','arrived'):
                value=getattr(queue,key,None)
                if value is not None:setattr(queue,key,value+elapsed)
        for key in ('gesture_started','idle_started','standby_settled_at'):
            value=getattr(app,key,None)
            if value is not None:setattr(app,key,value+elapsed)
        for key in ('rest_transition','sensor_reaction'):
            state=getattr(app,key,None)
            if state:state['started']+=elapsed
        previous['last_tick']=now
    if eligible:
        if previous is None:
            app.speech_reaction=dict(sequence=sequence,started=now,last_tick=now)
            app.audit_activity('speech_animation_started',animation='talking')
        return True
    if previous:
        app.speech_reaction=None
        app.audit_activity('speech_animation_completed',animation='talking')
    return False

def frame(reaction, now=None):
    now=time.monotonic() if now is None else now
    sequence=reaction['sequence']
    index=max(0,int((now-reaction['started'])*sequence['fps']))%len(sequence['frames'])
    return sequence['frames'][index]
