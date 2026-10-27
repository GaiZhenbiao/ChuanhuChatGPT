"""User-scoped new-session preferences; separate from active session snapshots."""
import json
import os
from pathlib import Path
from uuid import uuid4
from modules.agent.tools import DEFAULT_SETTINGS, validate_settings


def _path(root, owner):
    if not owner or any(c not in 'abcdef0123456789' for c in owner):
        raise ValueError('无效用户身份')
    return Path(root) / 'agent_data' / owner / 'settings.json'


def load_settings(root, owner):
    path = _path(root, owner)
    if not path.exists(): return validate_settings({})
    if path.is_symlink(): raise ValueError('配置文件不能是符号链接')
    with path.open(encoding='utf-8') as source: return validate_settings(json.load(source))


def save_settings(root, owner, settings):
    settings = validate_settings(settings)
    path = _path(root, owner)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix('.' + uuid4().hex + '.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as output: json.dump(settings, output, ensure_ascii=False)
    temporary.replace(path)
    return settings
