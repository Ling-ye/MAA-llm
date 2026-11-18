"""Portable paths. Reading example configuration never authorizes execution."""
from pathlib import Path
import datetime as dt
import json

PROJECT = Path(__file__).resolve().parents[1]
POLICIES = PROJECT / 'policies'
VERSIONS = {'arknights': 'v6.22.0', 'gf2': 'v2.8.4', 'endfield': 'v3.1.0'}

def config_path(name):
    local = PROJECT / 'config.local' / name
    return local if local.is_file() else PROJECT / 'config.example' / name

def settings():
    return json.loads(config_path('runtime.json').read_text(encoding='utf-8-sig'))

def resolve_user_path(value):
    path = Path(value).expanduser()
    return (path if path.is_absolute() else PROJECT/path).resolve()

def install_path(game):
    value = settings().get('installations', {}).get(game)
    return resolve_user_path(value) if value else PROJECT / 'tools' / game / VERSIONS[game]

def configured_path(key):
    value = settings().get('paths', {}).get(key)
    if not value:
        raise RuntimeError('Set paths.' + key + ' in config.local/runtime.json')
    return resolve_user_path(value)

def require_execution(game):
    """New checkouts cannot replay an already-used game day by default."""
    local = PROJECT / 'config.local' / 'runtime.json'
    if not local.is_file():
        raise RuntimeError('Initialize and review config.local/runtime.json before execution')
    data = settings()
    activation = data.get('execution', {}).get(game, {})
    if activation.get('enabled') is not True:
        raise RuntimeError('Execution is disabled for ' + game)
    earliest = dt.date.fromisoformat(activation.get('not_before_game_day', ''))
    today = (dt.datetime.now(dt.timezone(dt.timedelta(hours=8))) - dt.timedelta(hours=4)).date()
    if today < earliest:
        raise RuntimeError('Execution is not yet enabled for this game day')
