"""Resolve flexible app actions against placements in the current scene only."""
import random


def resolve_action_placement(cfg, action, sequences, reachable=None, choose=random.choice, current=None):
    mode = action.get('target_mode', 'specific')
    if mode == 'current':
        if current is None:
            raise ValueError('Current character position is required')
        role = action.get('animation')
        sequence = sequences.get('idle_side' if role == 'idle' else role)
        if not sequence or sequence.get('transition_only'):
            raise ValueError('Choose an available animation')
        scene = cfg.get('active_scene') or cfg.get('theme')
        if sequence.get('allowed_scenes') and scene not in sequence['allowed_scenes']:
            raise ValueError('Animation is not allowed in the current scene')
        result = dict(action, x=current[0], y=current[1])
        for key in ('spot_id','scene','target_scene','target_prop'):
            result.pop(key,None)
        return result
    if mode == 'specific':
        return dict(action)
    if mode not in ('gesture', 'location', 'any'):
        raise ValueError('Unknown action targeting mode')
    if mode == 'gesture' and not action.get('animation'):
        raise ValueError('Choose a gesture for this action')
    if mode == 'location' and not action.get('spot_id'):
        raise ValueError('Choose a location for this action')
    scene = cfg.get('active_scene') or cfg.get('theme')
    candidates = []
    for spot in cfg.get('interaction_spots', []):
        if mode == 'location' and spot.get('id') != action['spot_id']:
            continue
        if reachable and not reachable(spot):
            continue
        roles = list(dict.fromkeys([spot.get('animation')] + spot.get('animations', [])))
        for role in roles:
            sequence = sequences.get(role)
            if not role or not sequence or role.startswith('walk') or sequence.get('transition_only'):
                continue
            if mode == 'gesture' and role != action['animation']:
                continue
            if sequence.get('allowed_scenes') and scene not in sequence['allowed_scenes']:
                continue
            if sequence.get('entry_transition') and not all(sequence.get(k) in sequences for k in ('entry_transition', 'exit_transition')):
                continue
            rule = cfg.get('pose_rules', {}).get(role, {})
            if 'valid_spots' in rule and spot.get('id') not in rule['valid_spots']:
                continue
            candidates.append((spot, role))
    if not candidates:
        raise ValueError('No reachable matching gesture placement in this scene')
    spot, role = choose(candidates)
    return dict(action, spot_id=spot['id'], animation=role, x=spot['x'], y=spot['y'], facing=spot.get('facing', 'right'))
