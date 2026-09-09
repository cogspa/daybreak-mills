"""Local pairing and bounded validation shared by bridge and folder imports."""
import json
import os
import secrets
import stat
import zipfile

MAX_UPLOAD = 256 * 1024 * 1024
MAX_EXPANDED = 512 * 1024 * 1024
MAX_ENTRIES = 129
MAX_JSON = 1024 * 1024
KEY_NAME = 'bridge-pairing.json'


def pairing_key(folder):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, KEY_NAME)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        with open(path) as f:
            token = json.load(f)['token']
        if not isinstance(token, str) or len(token) != 64:
            raise ValueError('Invalid bridge pairing file; remove it to pair again')
        os.chmod(path, 0o600)
        return token
    token = secrets.token_hex(32)
    with os.fdopen(fd, 'w') as f:
        json.dump({'format': 'daybreak-pairing/1', 'token': token}, f)
    return token


def validate_range(zf):
    """Reject paths, links, bombs and incomplete manifests before extraction."""
    infos = zf.infolist()
    names = [i.filename for i in infos]
    if len(infos) > MAX_ENTRIES or len(set(names)) != len(names):
        raise ValueError('Too many or duplicate archive entries')
    if sum(i.file_size for i in infos) > MAX_EXPANDED:
        raise ValueError('Expanded archive exceeds 512 MiB')
    for i in infos:
        if (not i.filename or '/' in i.filename or '\\' in i.filename
                or ':' in i.filename or i.filename.startswith('.')
                or not i.filename.endswith(('.json', '.png'))
                or stat.S_ISLNK(i.external_attr >> 16) or i.flag_bits & 1):
            raise ValueError('Archive must contain only flat JSON and PNG files')
        if i.filename.endswith('.json') and i.file_size > MAX_JSON:
            raise ValueError('JSON entry exceeds 1 MiB')
    def read_json(name):
        try:
            value = json.loads(zf.read(name))
        except (KeyError, UnicodeError, json.JSONDecodeError) as e:
            raise ValueError('Missing or invalid JSON') from e
        if not isinstance(value, dict):
            raise ValueError('Expected a JSON object')
        return value
    manifest = read_json('range.json')
    jobs = manifest.get('jobs')
    if manifest.get('format') != 'daybreak-range/1' or not isinstance(jobs, list) or not 1 <= len(jobs) <= 64:
        raise ValueError('Invalid range manifest')
    expected = {'range.json'}
    for item in jobs:
        if not isinstance(item, dict):
            raise ValueError('Invalid job entry')
        job, texture = item.get('job'), item.get('texture')
        if (not isinstance(job, str) or not job.endswith('_job.json')
                or not isinstance(texture, str) or not texture.endswith('.png')
                or job not in names or texture not in names or job in expected):
            raise ValueError('Missing or duplicate job/texture')
        data = read_json(job)
        if data.get('format') != 'daybreak-job/1' or data.get('texture') != texture:
            raise ValueError('Job texture does not match manifest')
        with zf.open(texture) as f:
            if f.read(8) != b'\x89PNG\r\n\x1a\n':
                raise ValueError('Invalid PNG signature')
            # Streaming also verifies CRCs without allocating the whole image.
            tail = b''
            while chunk := f.read(65536):
                tail = (tail + chunk)[-12:]
            if tail != b'\x00\x00\x00\x00IEND\xaeB`\x82':
                raise ValueError('Incomplete PNG')
        expected.update((job, texture))
    if expected != set(names):
        raise ValueError('Unlisted archive entries')
    return manifest
