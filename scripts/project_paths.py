"""Portable paths. Reading example configuration never authorizes execution."""
from pathlib import Path
import datetime as dt
import json
import re

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

def select_transport(game, transport='mumu'):
    if game not in VERSIONS:
        raise ValueError('Unknown game')
    if transport not in ('mumu', 'pc'):
        raise ValueError('Unknown transport')
    if game == 'arknights' and transport != 'mumu':
        raise ValueError('Arknights supports only the MuMu transport')
    return transport


def is_loopback_adb_serial(serial):
    match = re.fullmatch(r'127\.0\.0\.1:([0-9]{1,5})', serial) if isinstance(serial, str) else None
    return bool(match and 1 <= int(match[1]) <= 65535)


def supervised_mumu_handoff(game):
    return f'{game} on MuMu requires supervised guest steps: python scripts/mumu_daily.py plan --game {game}; no Windows client or native adapter was started'


def add_native_transport_argument(parser):
    parser.add_argument('--transport', choices=('mumu', 'pc'), default='mumu',
                        help='PC adapters require explicit --transport pc for execution; default is MuMu')


def require_native_pc(game, transport='mumu'):
    if select_transport(game, transport) != 'pc':
        raise ValueError(supervised_mumu_handoff(game) + '; use --transport pc only when specifically opting in to the Windows route')


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
