from __future__ import annotations
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from zipfile import ZipFile
import pytest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('update_module', HERE / 'updater.py')
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)


def fixture_root(tmp_path, monkeypatch):
    root = tmp_path / 'my_app'
    (root / 'static').mkdir(parents=True)
    (root / 'data').mkdir()
    (root / 'static' / 'updates.html').write_text('old page', encoding='utf-8')
    (root / 'data' / 'community.key').write_bytes(b'SECRET-KEEP')
    (root / 'data' / 'community.db').write_bytes(b'USER-DB-KEEP')
    (root / 'version.json').write_text(json.dumps({'app_id': u.APP_ID, 'version': '0.7.2'}))
    monkeypatch.setattr(u, 'ROOT', root)
    monkeypatch.setattr(u, 'VERSION_PATH', root / 'version.json')
    monkeypatch.setattr(u, 'UPDATES_DIR', root / 'updates')
    monkeypatch.setattr(u, 'BACKUP_DIR', root / 'updates' / 'backups')
    monkeypatch.setattr(u, 'INBOX', root / 'updates' / 'inbox')
    monkeypatch.setattr(u, 'live_server', lambda: False)
    return root


def patch(path, files, frm='0.7.2', to='0.7.3', tamper=False):
    m = {'app_id': u.APP_ID, 'from_version': frm, 'to_version': to,
         'notes': 'test update', 'files': {k: hashlib.sha256(v).hexdigest() for k,v in files.items()}}
    with ZipFile(path, 'w') as z:
        z.writestr('manifest.json', json.dumps(m))
        for k, value in files.items():
            z.writestr('files/' + k, value + (b'bad' if tamper else b''))
    return path


def test_update_and_rollback_preserve_user_data(tmp_path, monkeypatch):
    root = fixture_root(tmp_path, monkeypatch)
    zp = patch(tmp_path / 'release.zip', {'static/updates.html': b'new page', 'static/new.js': b'console.log(1)'})
    backup = u.apply_patch(zp)
    assert u.current_version() == '0.7.3'
    assert (root / 'static' / 'updates.html').read_text() == 'new page'
    assert (root / 'static' / 'new.js').exists()
    assert (root / 'data' / 'community.key').read_bytes() == b'SECRET-KEEP'
    assert (root / 'data' / 'community.db').read_bytes() == b'USER-DB-KEEP'
    assert (backup / 'data' / 'community.db').exists()
    u.rollback(backup)
    assert u.current_version() == '0.7.2'
    assert (root / 'static' / 'updates.html').read_text() == 'old page'
    assert not (root / 'static' / 'new.js').exists()
    assert (root / 'data' / 'community.db').read_bytes() == b'USER-DB-KEEP'


def test_wrong_version_refused_before_any_write(tmp_path, monkeypatch):
    root = fixture_root(tmp_path, monkeypatch)
    zp = patch(tmp_path / 'wrong.zip', {'static/updates.html': b'new'}, frm='0.7.1')
    with pytest.raises(ValueError, match='Incompatible'):
        u.apply_patch(zp)
    assert (root / 'static' / 'updates.html').read_text() == 'old page'


def test_tampered_patch_refused(tmp_path, monkeypatch):
    root = fixture_root(tmp_path, monkeypatch)
    zp = patch(tmp_path / 'corrupt.zip', {'static/updates.html': b'changed'}, tamper=True)
    with pytest.raises(ValueError, match='Checksum'):
        u.apply_patch(zp)
    assert u.current_version() == '0.7.2'


def test_path_traversal_refused(tmp_path, monkeypatch):
    fixture_root(tmp_path, monkeypatch)
    zp = patch(tmp_path / 'unsafe.zip', {'../../outside.py': b'bad'})
    with pytest.raises(ValueError, match='Disallowed'):
        u.apply_patch(zp)
    assert not (tmp_path / 'outside.py').exists()


def test_data_replacement_refused(tmp_path, monkeypatch):
    root = fixture_root(tmp_path, monkeypatch)
    zp = patch(tmp_path / 'data.zip', {'data/community.db': b'NO'})
    with pytest.raises(ValueError, match='Disallowed'):
        u.apply_patch(zp)
    assert (root / 'data' / 'community.db').read_bytes() == b'USER-DB-KEEP'


def test_open_server_refused(tmp_path, monkeypatch):
    fixture_root(tmp_path, monkeypatch)
    monkeypatch.setattr(u, 'live_server', lambda: True)
    zp = patch(tmp_path / 'release.zip', {'static/updates.html': b'new'})
    with pytest.raises(ValueError, match='Close'):
        u.apply_patch(zp)


def test_reapply_refused(tmp_path, monkeypatch):
    fixture_root(tmp_path, monkeypatch)
    zp = patch(tmp_path / 'release.zip', {'static/updates.html': b'new'})
    u.apply_patch(zp)
    with pytest.raises(ValueError, match='Incompatible'):
        u.apply_patch(zp)
