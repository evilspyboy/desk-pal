"""Brief visual interruption: preserve destinations/queue, pause playback clocks."""
import math,time

def begin(app,action,now=None):
    now=time.monotonic() if now is None else now
    queue=getattr(app,'activity_queue',None)
    if (getattr(app,'sensor_reaction',None) or app.is_sleeping or app.edit_mode
        or getattr(app,'active_popup_modal',None) or getattr(app,'pending_popup_modal',None)
        or getattr(app,'tv_viewer',None) or getattr(app,'active_game_overlay',None) or getattr(app,'show_shutdown_modal',False)
        or getattr(app,'active_rest_role',None) or getattr(app,'rest_transition',None)):
        return False
    if queue and queue.active and (queue.active[0].get('_attention_waiting') or queue.active[0].get('_button_action')):
        return False
    role=action.get('animation');sequence=app.character_sequences.get(role)
    if not sequence or sequence.get('transition_only'):return False
    frames=sequence['frames'];fps=sequence['fps']
    limit=app.sequence_tick_limit(sequence)
    duration=limit/fps if math.isfinite(limit) else float(action.get('duration_seconds') or len(frames)/fps)
    facing=action.get('facing')
    app.sensor_reaction=dict(role=role,started=now,duration=max(.25,min(8,duration)),sequence=sequence,
        facing_left=app.facing_left if not facing else facing=='left')
    app.audit_activity('sensor_interrupted',animation=role,destination=[app.target_x,app.target_y])
    return True

def tick(app,now=None):
    now=time.monotonic() if now is None else now
    reaction=getattr(app,'sensor_reaction',None)
    if not reaction:return False
    blocked=app.is_sleeping or app.edit_mode or getattr(app,'active_popup_modal',None) or getattr(app,'tv_viewer',None) or getattr(app,'active_game_overlay',None)
    if not blocked and now-reaction['started']<reaction['duration']:return True
    elapsed=now-reaction['started']
    queue=getattr(app,'activity_queue',None)
    if queue:
        for name in ('started','arrived'):
            value=getattr(queue,name,None)
            if value is not None:setattr(queue,name,value+elapsed)
    for name in ('gesture_started','idle_started'):
        value=getattr(app,name,None)
        if value is not None:setattr(app,name,value+elapsed)
    app.sensor_reaction=None
    app.audit_activity('sensor_resumed',animation=reaction['role'],destination=[app.target_x,app.target_y])
    return False

def frame(reaction,now=None):
    now=time.monotonic() if now is None else now
    sequence=reaction['sequence'];frames=sequence['frames'];n=len(frames)
    index=max(0,int((now-reaction['started'])*sequence['fps']))
    mode=sequence.get('playback_mode','once')
    if mode=='ping_pong' and n>1:
        index%=2*n-2;index=index if index<n else 2*n-2-index
    elif mode in ('loop','repeat'):index%=n
    else:index=min(index,n-1)
    return frames[index]
