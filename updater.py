"""Offline, per-version patch updater for the local Community Windows prototype.

Security: install only packages the operator obtained from a trusted channel.
This verifies file integrity *within a package*, not publisher authenticity.
Stop the app before applying; never distribute /data, secrets or .venv.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import socket
import sys
import tempfile
from datetime import datetime, timezone
from zipfile import ZipFile, BadZipFile

ROOT = Path(__file__).resolve().parent
APP_ID = 'affiliate-auto-studio-community'
VERSION_PATH = ROOT / 'version.json'
UPDATES_DIR = ROOT / 'updates'
BACKUP_DIR = UPDATES_DIR / 'backups'
INBOX = UPDATES_DIR / 'inbox'
MAX_PAYLOAD_SIZE = 40 * 1024 * 1024
MAX_FILE_SIZE = 12 * 1024 * 1024


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def current_version() -> str:
    obj = json.loads(VERSION_PATH.read_text(encoding='utf-8'))
    if obj.get('app_id') != APP_ID:
        raise ValueError('Wrong application directory')
    return obj['version']


def valid_path(name: str) -> bool:
    p = PurePosixPath(name)
    if (not name or '\\' in name or name.startswith('/') or ':' in name or
            '..' in p.parts or '.' in p.parts or name.endswith('/') or len(p.parts) > 6):
        return False
    if len(p.parts) == 1:
        return name in {'community_app.py', 'promote_admin.py', 'requirements.txt',
                        'README_TH.md', 'run_windows.bat', 'run_mac_linux.sh', 'updater.py', 'version.json'}
    if p.parts[0] == 'static' and len(p.parts) >= 2:
        return p.suffix in {'.html', '.css', '.js', '.svg'}
    if p.parts[0] == 'studio_v6' and len(p.parts) in (2, 3):
        if any(part in ('data', '.venv', 'updates', '__pycache__') for part in p.parts): return False
        if p.name.startswith('.') or p.name == '.env': return False
        return p.suffix in {'.py','.js','.css','.html','.csv','.txt'}
    return False


def live_server() -> bool:
    # Port for this prototype, not an all-purpose detection for server processes.
    try:
        with socket.create_connection(('127.0.0.1', 8010), timeout=0.25):
            return True
    except OSError:
        return False


def patch_zip(path: Path, from_version: str):
    """Validate manifest + every payload before mutating the installed tree."""
    if not path.is_file():
        raise ValueError('Patch file not found')
    if path.stat().st_size > MAX_PAYLOAD_SIZE:
        raise ValueError('Patch exceeds size limit')
    try:
        with ZipFile(path) as z:
            names = z.namelist()
            if len(names) != len(set(names)) or 'manifest.json' not in names:
                raise ValueError('Missing manifest or duplicate ZIP entries')
            m = json.loads(z.read('manifest.json'))
            if (m.get('app_id') != APP_ID or m.get('from_version') != from_version or
                    not isinstance(m.get('to_version'), str) or
                    m['to_version'] == from_version):
                raise ValueError('Incompatible patch: app ID or source version mismatch')
            version_string = m['to_version']
            def digits(v):
                if not isinstance(v, str) or not all(x.isdigit() for x in v.split('.')) or len(v.split('.')) != 3:
                    raise ValueError('Version must be numeric X.Y.Z')
                return tuple(map(int, v.split('.')))
            if digits(version_string) <= digits(from_version):
                raise ValueError('Patch must upgrade to a newer version')
            files = m.get('files')
            if not isinstance(files, dict) or not files or len(files) > 200:
                raise ValueError('Invalid file manifest')
            expected_names = {'manifest.json'} | {'files/' + n for n in files}
            if set(names) != expected_names:
                raise ValueError('Unexpected file(s) in update package')
            output = {}
            total = 0
            for n, claimed_digest in files.items():
                if not valid_path(n):
                    raise ValueError('Disallowed patch destination: ' + n)
                info = z.getinfo('files/' + n)
                if info.is_dir() or info.file_size > MAX_FILE_SIZE or info.compress_size > MAX_FILE_SIZE:
                    raise ValueError('Invalid patch file size: ' + n)
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('Symlinks are not allowed')
                data = z.read(info)
                total += len(data)
                if total > MAX_PAYLOAD_SIZE:
                    raise ValueError('Patch uncompressed size exceeds limit')
                if not isinstance(claimed_digest, str) or sha256(data) != claimed_digest:
                    raise ValueError('Checksum mismatch: ' + n)
                output[n] = data
            return m, output
    except BadZipFile as e:
        raise ValueError('Invalid ZIP file') from e


def write_json_atomic(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.new')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)


def replace_file(dest: Path, contents: bytes):
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix='.update-', dir=str(dest.parent))
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(contents)
        os.replace(temp_name, dest)
    finally:
        if os.path.exists(temp_name): os.unlink(temp_name)


def apply_patch(zip_path: Path):
    if live_server():
        raise ValueError('Close the V7 Community server window (port 8010) before updating')
    previous = current_version()
    manifest, files = patch_zip(zip_path, previous)
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_DIR / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + previous.replace('.', '-'))
    if backup.exists():
        raise ValueError('Backup folder exists; retry in a second')
    backup.mkdir(parents=True)
    saved_files = []
    record = {'app_id': APP_ID, 'from_version': previous, 'to_version': manifest['to_version'],
              'changed_files': [], 'created_at': datetime.now(timezone.utc).isoformat(),
              'state': 'preparing'}
    try:
        # Snapshot the database and encryption key while server is stopped.
        if (ROOT / 'data').exists():
            shutil.copytree(ROOT / 'data', backup / 'data', symlinks=False)
        for rel in files:
            target = ROOT / rel
            existed = target.exists()
            if existed:
                origin = backup / 'code' / rel
                origin.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, origin)
            saved_files.append((rel, existed))
            record['changed_files'].append({'path': rel, 'existed': existed})
        shutil.copy2(VERSION_PATH, backup / 'old_version.json')
        record['state'] = 'installing'
        write_json_atomic(backup / 'record.json', record)
        for rel, content in files.items():
            replace_file(ROOT / rel, content)
        write_json_atomic(VERSION_PATH, {'app_id': APP_ID, 'version': manifest['to_version']})
        record['state'] = 'installed'
        write_json_atomic(backup / 'record.json', record)
    except Exception:
        # Undo code writes; leave data untouched because app did not run during update.
        for rel, existed in reversed(saved_files):
            target = ROOT / rel
            source = backup / 'code' / rel
            if existed and source.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            elif not existed and target.exists():
                target.unlink()
        if (backup / 'old_version.json').exists():
            shutil.copy2(backup / 'old_version.json', VERSION_PATH)
        record['state'] = 'failed_restored'
        write_json_atomic(backup / 'record.json', record)
        raise
    return backup


def rollback(backup: Path):
    if live_server():
        raise ValueError('Stop the server before rolling back')
    backup = backup.resolve()
    if backup.parent != BACKUP_DIR.resolve():
        raise ValueError('Backup path must be inside updates/backups')
    record = json.loads((backup / 'record.json').read_text(encoding='utf-8'))
    if record.get('app_id') != APP_ID or record.get('state') != 'installed':
        raise ValueError('This backup is not a completed install')
    if current_version() != record['to_version']:
        raise ValueError('Rollback requires the exact installed version from the backup')
    for entry in reversed(record['changed_files']):
        rel = entry['path']
        if not valid_path(rel): raise ValueError('Unexpected rollback path')
        dest = ROOT / rel
        if entry['existed']:
            shutil.copy2(backup / 'code' / rel, dest)
        elif dest.exists():
            dest.unlink()
    shutil.copy2(backup / 'old_version.json', VERSION_PATH)
    record['state'] = 'rolled_back'
    write_json_atomic(backup / 'record.json', record)
    # Do not restore the data snapshot by default, to avoid erasing user activity.


def main():
    parser = argparse.ArgumentParser(description='Affiliate Auto Studio Windows local updater')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('status')
    a = sub.add_parser('apply'); a.add_argument('zip_file', nargs='?')
    r = sub.add_parser('rollback'); r.add_argument('backup_dir')
    args = parser.parse_args()
    try:
        if args.command == 'status':
            print('Installed version:', current_version())
            print('Place trusted patch ZIPs in:', INBOX)
        elif args.command == 'apply':
            if args.zip_file:
                chosen = Path(args.zip_file)
            else:
                INBOX.mkdir(parents=True, exist_ok=True)
                found = list(INBOX.glob('*.zip'))
                if len(found) != 1:
                    raise ValueError('Put exactly one downloaded patch ZIP in updates/inbox, then retry')
                chosen = found[0]
            backup = apply_patch(chosen)
            print('SUCCESS. Updated to version', current_version())
            print('Backup saved:', backup)
            print('Start run_windows.bat to use the new version.')
        else:
            rollback(Path(args.backup_dir))
            print('Rolled back code to version', current_version(), '. User data was NOT overwritten.')
        return 0
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print('UPDATE FAILED:', exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
