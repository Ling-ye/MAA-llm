"""Install pinned upstream ZIP releases. No binaries, login, UAC or games are run."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import urllib.parse
import urllib.request
import zipfile
from project_paths import PROJECT, POLICIES

REPOSITORIES = {
    'arknights': 'MaaAssistantArknights/MaaAssistantArknights',
    'gf2': 'DarkLingYun/MaaGF2Exilium',
    'endfield': 'MaaEnd/MaaEnd',
}
ALLOWED_HOSTS = {'github.com', 'api.github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}
MAX_DOWNLOAD = 1024 * 1024 * 1024
MAX_UNPACKED = 4 * MAX_DOWNLOAD
MAX_ENTRIES = 100000

def safe_url(url):
    u = urllib.parse.urlsplit(url)
    if u.scheme != 'https' or u.hostname not in ALLOWED_HOSTS or u.username or u.password or u.port not in (None, 443):
        raise ValueError('Only HTTPS official GitHub release hosts are allowed')
    return url

class Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def open_url(url):
    req = urllib.request.Request(safe_url(url), headers={'User-Agent': 'MAA-llm-bootstrap', 'Accept': 'application/vnd.github+json'})
    return urllib.request.build_opener(Redirects()).open(req, timeout=30)

def manifest(game):
    row = json.loads((POLICIES/'releases.json').read_text(encoding='utf8'))[game]
    if row['repository'] != REPOSITORIES[game] or not re.fullmatch(r'v\d+\.\d+\.\d+', row['tag']):
        raise ValueError('Unapproved repository or release tag')
    if Path(row['asset']).name != row['asset'] or not row['asset'].endswith('.zip') or '/' in row['asset'] or '\\' in row['asset']:
        raise ValueError('Invalid asset name')
    if not re.fullmatch('[0-9a-f]{64}', row['sha256']) or not 0 < row['size'] <= MAX_DOWNLOAD:
        raise ValueError('Missing checksum or invalid size')
    return row

def release_url(row):
    return f"https://github.com/{row['repository']}/releases/download/{row['tag']}/{row['asset']}"

def check_metadata(row, metadata):
    if metadata.get('tag_name') != row['tag'] or metadata.get('draft') or metadata.get('prerelease'):
        raise ValueError('Release identity/status changed')
    found = [a for a in metadata.get('assets', []) if a.get('name') == row['asset']]
    if len(found) != 1:
        raise ValueError('Expected exactly one pinned release asset')
    asset = found[0]
    if asset.get('browser_download_url') != release_url(row) or asset.get('size') != row['size']:
        raise ValueError('Release URL or size changed')
    if asset.get('digest') != 'sha256:' + row['sha256']:
        raise ValueError('Release SHA-256 is absent or differs; stop for review')

def verify_archive(path, row):
    if path.stat().st_size != row['size']:
        raise ValueError('Archive size mismatch')
    with path.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    if checksum != row['sha256']:
        raise ValueError('Archive SHA-256 mismatch')

def extract_checked(archive, destination):
    """Reject Windows traversal, ADS, symlinks, reserved names and ZIP bombs."""
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive) as z:
        entries = z.infolist()
        if len(entries) > MAX_ENTRIES or sum(i.file_size for i in entries) > MAX_UNPACKED:
            raise ValueError('Archive exceeds extraction limits')
        seen = set()
        for item in entries:
            name = item.filename
            parts = PurePosixPath(name).parts
            if not parts or name.startswith('/') or '\\' in name or ':' in name or any(p in ('.', '..') or p.endswith((' ', '.')) for p in parts):
                raise ValueError('Unsafe archive path')
            if any(re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\..*)?', p) for p in parts):
                raise ValueError('Reserved Windows filename')
            if stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError('Archive symlinks are forbidden')
            key = name.rstrip('/').casefold()
            if key in seen:
                raise ValueError('Duplicate archive destination')
            seen.add(key)
            target = destination.joinpath(*parts).resolve()
            target.relative_to(destination)
        # No files are written until every entry has passed validation.
        for item in entries:
            target = destination.joinpath(*PurePosixPath(item.filename).parts)
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(item) as source, target.open('xb') as sink:
                    shutil.copyfileobj(source, sink, 1024*1024)

def download(game):
    row = manifest(game)
    destination = PROJECT/'tools'/game/row['tag']
    destination.resolve().relative_to((PROJECT/'tools').resolve())
    if destination.exists():
        raise FileExistsError('Installation already exists; never overwrite or downgrade it')
    with open_url(f"https://api.github.com/repos/{row['repository']}/releases/tags/{row['tag']}") as response:
        raw = response.read(4*1024*1024+1)
    if len(raw) > 4*1024*1024:
        raise ValueError('Release metadata too large')
    check_metadata(row, json.loads(raw))
    cache = PROJECT/'downloads'
    cache.mkdir(exist_ok=True)
    archive = cache/row['asset']
    if not archive.exists():
        # Preserve failed partial downloads for inspection, never execute them.
        with tempfile.NamedTemporaryFile(dir=cache, suffix='.partial', delete=False) as sink:
            partial = Path(sink.name)
            total = 0
            with open_url(release_url(row)) as response:
                while block := response.read(1024*1024):
                    total += len(block)
                    if total > row['size']:
                        raise ValueError('Download exceeds pinned size')
                    sink.write(block)
        verify_archive(partial, row)
        if archive.exists():
            raise FileExistsError('Another download completed; review cache')
        partial.rename(archive)
    verify_archive(archive, row)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.unpack-', dir=destination.parent))/'payload'
    extract_checked(archive, staging)
    entries = list(staging.rglob(row['entry']))
    if len(entries) != 1:
        raise ValueError('Expected executable missing or ambiguous; extracted files left for review')
    app = entries[0].parent
    if game != 'arknights':
        actual = json.loads((app/'interface.json').read_text(encoding='utf-8-sig')).get('version')
        if actual != row['tag']:
            raise ValueError('Extracted manifest version mismatch')
    if destination.exists():
        raise FileExistsError('Concurrent install; refusing overwrite')
    app.rename(destination)
    return {'installed': str(destination), 'sha256_verified': True, 'launched': False}

def initialize():
    local = PROJECT/'config.local'
    local.mkdir(exist_ok=True)
    created = []
    for source in sorted((PROJECT/'config.example').glob('*.json')):
        target = local/source.name
        if target.exists():
            continue
        with target.open('xb') as out:
            out.write(source.read_bytes())
        created.append(target.name)
    return {'created': created, 'execution_enabled': False}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'download'])
    parser.add_argument('--game', choices=REPOSITORIES)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    if args.action == 'download' and not args.game:
        parser.error('download requires --game')
    if not args.execute:
        result = {'mode': 'plan_only', 'action': args.action, 'game': args.game}
        if args.game:
            result.update(manifest(args.game), url=release_url(manifest(args.game)))
    else:
        result = initialize() if args.action == 'init' else download(args.game)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'status': 'blocked', 'error': str(exc)}))
        raise SystemExit(2)
