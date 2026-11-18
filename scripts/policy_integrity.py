"""Detect accidental changes to reviewed local policies; hashes are not signatures."""
import hashlib
import json
from project_paths import POLICIES

def read_policy(name):
    path = (POLICIES/name).resolve()
    path.relative_to(POLICIES.resolve())
    hashes = json.loads((POLICIES/'hashes.json').read_text(encoding='utf8'))
    expected = hashes[name]
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('Reviewed policy changed: ' + name)
    return json.loads(data)
