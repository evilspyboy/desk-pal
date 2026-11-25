"""Versioned settings/content backups. Code, credentials and runtime logs stay outside."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
import time
import zipfile

MAX_BYTES = 512 * 1024 * 1024
AUXILIARY = {'sprite_tags.json', 'skeleton_annotations.json', 'skeleton_frame_sources.json', 'puppet_rig.json', 'ai_settings.json', 'hardware_settings.json'}
EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.json', '.md', '.txt'}
SECRETS = {'password', 'client_secret', 'api_key', 'apikey', 'access_token', 'refresh_token', 'authorization', 'secret', 'token'}


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if k.lower() not in SECRETS}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode('utf-8')


def export_backup(cfg, assets, config_dir):
    files = {'config/room_config.json': encoded(clean(cfg))}
    assets, config_dir = Path(assets), Path(config_dir)
    for path in sorted(assets.rglob('*')):
        if path.is_file() and not path.is_symlink() and path.suffix.lower() in EXTENSIONS:
            files['assets/' + path.relative_to(assets).as_posix()] = path.read_bytes()
    for name in AUXILIARY:
        path = config_dir / name
        if path.is_file():
            files['config/' + name] = encoded(clean(json.loads(path.read_text(encoding='utf-8'))))
    if sum(map(len, files.values())) > MAX_BYTES:
        raise ValueError('Backup exceeds the 512 MB content limit')
    manifest = dict(format='deskpal-backup', version=1, created_at=time.time(),
                    excludes=['application code', 'external application credentials/tokens', 'logs and telemetry'],
                    files={name: hashlib.sha256(data).hexdigest() for name, data in files.items()})
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', encoded(manifest))
        for name, data in files.items():
            archive.writestr(name, data)
    return output.getvalue()


def unpack(data):
    if len(data) > MAX_BYTES:
        raise ValueError('Archive exceeds 512 MB')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > 20000 or sum(e.file_size for e in entries) > MAX_BYTES:
            raise ValueError('Expanded archive exceeds the content limit')
        files = {}
        for entry in entries:
            name = entry.filename
            path = PurePosixPath(name)
            if '\\' in name or ':' in name or path.is_absolute() or '..' in path.parts or str(path) != name:
                raise ValueError('Unsafe archive path')
            if name in files or entry.is_dir() or stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:
                raise ValueError('Duplicate, directory, symbolic link or encrypted archive entry')
            if name != 'manifest.json' and not (
                name == 'config/room_config.json' or name in {'config/' + n for n in AUXILIARY} or
                name.startswith('assets/') and path.suffix.lower() in EXTENSIONS):
                raise ValueError('Archive contains unsupported files: ' + name)
            files[name] = archive.read(entry)
    manifest = json.loads(files.pop('manifest.json'))
    if manifest.get('format') != 'deskpal-backup' or manifest.get('version') != 1:
        raise ValueError('Unsupported backup format/version')
    if set(files) != set(manifest.get('files', {})):
        raise ValueError('Backup contents do not match its manifest')
    for name, body in files.items():
        if hashlib.sha256(body).hexdigest() != manifest['files'][name]:
            raise ValueError('Damaged backup file: ' + name)
    cfg = json.loads(files['config/room_config.json'])
    if not isinstance(cfg, dict) or not isinstance(cfg.get('scenes'), dict) or not isinstance(cfg.get('apps', []), list):
        raise ValueError('Backup settings have an unsupported structure')
    for key in ('characters', 'animation_sequences'):
        if not isinstance(cfg.get(key), dict):
            raise ValueError('Backup is missing ' + key)
    if cfg.get('active_scene') not in cfg['scenes'] or cfg.get('active_character') not in cfg['characters']:
        raise ValueError('Active scene or character is missing')
    for name in files:
        if name.startswith('config/'):
            json.loads(files[name])
    return manifest, cfg, files


def destination(name, assets, config_dir):
    root = Path(assets if name.startswith('assets/') else config_dir).resolve()
    relative = name.split('/', 1)[1]
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise ValueError('Destination escapes its content directory')
    return target


def missing_dependencies(cfg, files):
    missing = set()
    def visit(value):
        if isinstance(value, dict):
            for child in value.values(): visit(child)
        elif isinstance(value, list):
            for child in value: visit(child)
        elif isinstance(value, str) and value.startswith('/assets/'):
            from urllib.parse import unquote
            name = unquote(value[1:].split('?', 1)[0])
            if name not in files: missing.add(name)
    visit(cfg)
    for sid, scene in cfg['scenes'].items():
        name = 'assets/themes/' + scene.get('theme', sid) + '/' + scene.get('background', 'background.jpg')
        if name not in files: missing.add(name)
    for sequence in cfg['animation_sequences'].values():
        for frame in sequence.get('frames', []):
            name = frame.get('url') if isinstance(frame, dict) else frame
            if isinstance(name, str) and not name.startswith('/assets/'):
                options = [n for n in files if n.startswith('assets/characters/') and (n.endswith('/' + name) or n == 'assets/' + name)]
                if not options: missing.add('character frame: ' + name)
    for character in cfg['characters'].values():
        for sequence_id in character.get('animations', {}).values():
            if sequence_id not in cfg['animation_sequences']:
                missing.add('animation sequence: ' + str(sequence_id))
    return sorted(missing)


def preview_backup(data, current, assets, config_dir):
    manifest, cfg, files = unpack(data)
    changes = {'added': [], 'replaced': [], 'unchanged': []}
    state = {}
    for name, body in files.items():
        target = destination(name, assets, config_dir)
        if name == 'config/room_config.json':
            old = encoded(clean(current))
        else:
            old = target.read_bytes() if target.is_file() else None
        category = 'added' if old is None else 'unchanged' if old == body else 'replaced'
        state[name] = hashlib.sha256(old).hexdigest() if old is not None else None
        changes[category].append(name)
    section_changes = {}
    for section in ('scenes','characters','animation_sequences','apps'):
        before, after = current.get(section, {}), cfg.get(section, {})
        if isinstance(before, list): before = {v['id']:v for v in before}
        if isinstance(after, list): after = {v['id']:v for v in after}
        section_changes[section] = dict(added=sorted(set(after)-set(before)),
            removed=sorted(set(before)-set(after)),
            changed=sorted(k for k in set(after)&set(before) if clean(before[k]) != after[k]))
    return dict(version=manifest['version'], created_at=manifest['created_at'],
                digest=hashlib.sha256(data).hexdigest(), changes=changes,
                state_digest=hashlib.sha256(encoded(state)).hexdigest(),
                settings_changed=[k for k in cfg if clean(current).get(k) != cfg[k]],
                section_changes=section_changes,
                missing=missing_dependencies(cfg, files),
                counts={k:len(cfg.get(k, {})) for k in ('scenes','characters','animation_sequences','apps')},
                notes=['Full settings replacement; existing extra asset files are retained.',
                       'Code, logs and external OAuth tokens are not restored.',
                       'Personal addresses and paths are included: this is a private backup.'])


def keep_local_secrets(imported, current):
    if isinstance(imported, dict) and isinstance(current, dict):
        result = copy.deepcopy(imported)
        for key, value in current.items():
            if key.lower() in SECRETS:
                result[key] = copy.deepcopy(value)
            elif key in result:
                result[key] = keep_local_secrets(result[key], value)
        return result
    if isinstance(imported, list) and isinstance(current, list):
        by_id = {v['id']:v for v in current if isinstance(v, dict) and 'id' in v}
        return [keep_local_secrets(v, by_id.get(v.get('id'), {})) if isinstance(v, dict) else v for v in imported]
    return copy.deepcopy(imported)


def restore_backup(data, current, assets, config_dir, apply_config, expected_digest, expected_state):
    review = preview_backup(data, current, assets, config_dir)
    if review['digest'] != expected_digest or review['state_digest'] != expected_state or review['missing']:
        raise ValueError('Backup changed or has missing dependencies; preview it again')
    _, cfg, files = unpack(data)
    recovery_dir = Path(config_dir) / 'backups'
    recovery_dir.mkdir(parents=True, exist_ok=True)
    recovery = recovery_dir / ('before-restore-' + str(time.time_ns()) + '.zip')
    recovery.write_bytes(export_backup(current, assets, config_dir))
    original = {}
    def write(path, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.deskpal-restore-')
        try:
            with os.fdopen(fd, 'wb') as stream: stream.write(body)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
    try:
        for name in review['changes']['added'] + review['changes']['replaced']:
            if name == 'config/room_config.json': continue
            path = destination(name, assets, config_dir)
            original[path] = path.read_bytes() if path.is_file() else None
            write(path, files[name])
        apply_config(keep_local_secrets(cfg, current))
    except Exception:
        for path, body in original.items():
            if body is None: path.unlink(missing_ok=True)
            else: write(path, body)
        apply_config(current)
        raise
    return dict(status='ok', recovery_backup=recovery.name)
