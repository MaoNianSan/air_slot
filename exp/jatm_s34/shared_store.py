"""Atomic, content-checked annual data commits, with one writer per store."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile


def digest(value):
    # JSON object keys are strings on disk. Hash the same representation before
    # and after restoration (objective curves may use numerical action keys).
    value = json.loads(json.dumps(value, allow_nan=False))
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return 'sha256:' + h.hexdigest()


def code_hash(path):
    """Source identity survives Git's Windows/Linux newline conversion."""
    content = Path(path).read_bytes().replace(b'\r\n', b'\n')
    return 'sha256:' + hashlib.sha256(content).hexdigest()


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(payload, stream, sort_keys=True, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class SharedStore:
    def __init__(self, root, identity):
        self.root = Path(root)
        self.identity = identity
        self.identity_hash = digest(identity)
        self.root.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def writer(self):
        import psutil
        lock = self.root / 'WRITER.json'
        owner = dict(pid=os.getpid(), host=socket.gethostname(),
                     process_created=psutil.Process().create_time())
        try:
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            old = json.loads(lock.read_text())
            if old['host'] != owner['host']:
                raise RuntimeError('SHARED_WRITER_REMOTE_LOCK_REQUIRES_OWNER_CHECK')
            try:
                alive = psutil.Process(old['pid']).create_time() == old['process_created']
            except psutil.NoSuchProcess:
                alive = False
            if alive:
                raise RuntimeError('SHARED_WRITER_ALREADY_ACTIVE')
            lock.unlink()
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        with os.fdopen(fd, 'w') as stream:
            json.dump(owner, stream)
        try:
            yield self
        finally:
            lock.unlink(missing_ok=True)

    def read(self, key):
        path = self.root / (key + '.json')
        if not path.exists():
            return None
        saved = json.loads(path.read_text(encoding='utf-8'))
        claimed = saved.pop('artifact_hash')
        if claimed != digest(saved) or not saved.get('complete'):
            raise ValueError('SHARED_COMMIT_CORRUPT:' + key)
        if saved['identity_hash'] != self.identity_hash:
            raise ValueError('SHARED_IDENTITY_MISMATCH:' + key)
        return saved['payload']

    def commit(self, key, payload):
        previous = self.read(key)
        if previous is not None:
            if digest(previous) != digest(payload):
                raise ValueError('SHARED_IMMUTABLE_CONFLICT:' + key)
            return
        saved = dict(schema_version='JATM_SHARED_COMMIT_V1', complete=True,
                     identity_hash=self.identity_hash, identity=self.identity,
                     created_at=datetime.now(timezone.utc).isoformat(), payload=payload)
        saved['artifact_hash'] = digest(saved)
        atomic_json(self.root / (key + '.json'), saved)
