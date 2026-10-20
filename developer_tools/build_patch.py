"""Developer-only: create an offline incremental ZIP, not a signed production release.

Example:
 python developer_tools/build_patch.py --old "C:/studio-v7.2" --new "C:/studio-v7.3" --output "C:/releases/update_0.7.2_to_0.7.3.zip"

Never distribute backup/data/API keys. Do not treat the ZIP checksum as authentication.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from updater import APP_ID, valid_path


def make_patch(old: Path, new: Path, output: Path):
    old_version = json.loads((old / 'version.json').read_text(encoding='utf-8'))
    new_version = json.loads((new / 'version.json').read_text(encoding='utf-8'))
    if old_version['app_id'] != APP_ID or new_version['app_id'] != APP_ID:
        raise ValueError('Wrong app ID')
    if old_version['version'] == new_version['version']:
        raise ValueError('Bump the version in version.json before releasing')
    files = {}
    for source in new.rglob('*'):
        if not source.is_file() or source.is_symlink(): continue
        rel = source.relative_to(new).as_posix()
        if not valid_path(rel): continue
        previous = old / rel
        contents = source.read_bytes()
        if not previous.is_file() or previous.read_bytes() != contents:
            files[rel] = contents
    if not files:
        raise ValueError('No code changes found')
    manifest = {'app_id': APP_ID, 'from_version': old_version['version'],
                'to_version': new_version['version'],
                'files': {name: hashlib.sha256(content).hexdigest() for name, content in sorted(files.items())}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'w', ZIP_DEFLATED) as z:
        z.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        for name, content in sorted(files.items()):
            z.writestr('files/' + name, content)
    print('Created', output, 'with', len(files), 'changed file(s)')
    print('SHA256 of ZIP (publish through a separate trusted channel):', hashlib.sha256(output.read_bytes()).hexdigest())


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--old', type=Path, required=True)
    p.add_argument('--new', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    make_patch(args.old.resolve(), args.new.resolve(), args.output.resolve())
