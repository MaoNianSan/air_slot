"""Bind an extracted source-only archive to its reviewed Git commit."""
import argparse
import re
from pathlib import Path

from exp.jatm_s34.shared_store import atomic_json


def prepare(root, git_head, archive_sha256):
    root = Path(root).resolve()
    if not re.fullmatch(r'[0-9a-f]{40}', git_head):
        raise ValueError('SOURCE_SNAPSHOT_GIT_HEAD_INVALID')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', archive_sha256):
        raise ValueError('SOURCE_SNAPSHOT_ARCHIVE_HASH_INVALID')
    snapshot = root / 'CODE_SNAPSHOT.json'
    payload = dict(schema_version='JATM_CODE_SNAPSHOT_V1', git_head=git_head,
                   source_archive_sha256=archive_sha256)
    if snapshot.exists():
        import json
        if json.loads(snapshot.read_text(encoding='utf-8')) != payload:
            raise FileExistsError('SOURCE_SNAPSHOT_IDENTITY_CONFLICT')
        return payload
    atomic_json(snapshot, payload)
    return payload


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--git-head', required=True)
    parser.add_argument('--source-archive-sha256', required=True)
    args = parser.parse_args()
    prepare(args.root, args.git_head, args.source_archive_sha256)
