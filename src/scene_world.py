"""Scene-local configuration and portal graph, independent of the display."""
from copy import deepcopy
from collections import deque

FIELDS = ('walkable_trapezoid', 'obstacles', 'props', 'interaction_spots', 'pose_rules')

def scene_id(cfg):
    return cfg.get('active_scene') or cfg.get('theme', 'cozy_study')

def ensure_world(cfg):
    current = scene_id(cfg)
    scenes = cfg.setdefault('scenes', {})
    scene = scenes.setdefault(current, {'name': current.replace('_', ' ').title(), 'theme': cfg.get('theme', current), 'portals': []})
    legacy = cfg.get('scene_placements', {}).get(current, {})
    for key in FIELDS:
        scene.setdefault(key, deepcopy(legacy.get(key, cfg.get(key, {} if key in ('walkable_trapezoid', 'pose_rules') else []))))
    cfg.setdefault('scene_links', [])
    cfg['active_scene'] = current
    return scenes

def sync_scene(cfg):
    scene = ensure_world(cfg)[scene_id(cfg)]
    for key in FIELDS:
        scene[key] = deepcopy(cfg.get(key, {} if key in ('walkable_trapezoid', 'pose_rules') else []))
    cfg.setdefault('scene_placements', {})[scene_id(cfg)] = {key: deepcopy(scene[key]) for key in ('interaction_spots', 'pose_rules')}

def activate_scene(cfg, destination):
    scenes = ensure_world(cfg)
    if destination not in scenes:
        raise ValueError('Unknown destination scene')
    scene = scenes[destination]
    if scene.get('enabled', True) is False:
        raise ValueError('That scene is disabled')
    cfg['active_scene'] = destination
    cfg['theme'] = scene.get('theme', destination)
    for key in FIELDS:
        cfg[key] = deepcopy(scene.get(key, {} if key in ('walkable_trapezoid', 'pose_rules') else []))
    sync_scene(cfg)

def portal(cfg, endpoint):
    return next((p for p in cfg.get('scenes', {}).get(endpoint.get('scene'), {}).get('portals', []) if p['id'] == endpoint.get('portal')), None)

def find_route(cfg, start, destination, reachable=None):
    """BFS over arrival portals, allowing different disconnected floor regions."""
    if destination not in cfg.get('scenes', {}):
        raise ValueError('Unknown destination scene')
    if any(cfg.get('scenes', {}).get(s, {}).get('enabled', True) is False for s in (start, destination)):
        raise ValueError('That scene is disabled')
    queue = deque([(start, None, [])])
    visited = {(start, None)}
    while queue:
        current, arrived, steps = queue.popleft()
        if current == destination:
            return steps
        for link in cfg.get('scene_links', []):
            for source, target in ((link['a'], link['b']), (link['b'], link['a'])):
                if source['scene'] != current or not portal(cfg, source) or not portal(cfg, target):
                    continue
                if cfg['scenes'][target['scene']].get('enabled', True) is False:
                    continue
                if reachable and not reachable(current, arrived, source['portal']):
                    continue
                state = (target['scene'], target['portal'])
                if state not in visited:
                    visited.add(state)
                    queue.append((state[0], state[1], steps + [{'from': source, 'to': target}]))
    raise ValueError('No walkable linked route to that scene')
