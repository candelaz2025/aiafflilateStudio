"""TikTok: Login Kit OAuth, token refresh, and the compliant Direct Post path, against dev_tools mock."""
import json
import re
import socket
import sqlite3
import threading
import time
from urllib.parse import unquote, urlsplit

import html as _html
import pytest
import requests
import uvicorn
from fastapi.testclient import TestClient

KEY = b'HCMiHM3FNUmDDvPGmUKpkTMKyvIWUZSdLHvufz1qUdc='


def free_port():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture(scope='module')
def mock_base():
    from dev_tools.mock_providers import app as mock_app
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(mock_app, host='127.0.0.1', port=port, log_level='warning'))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(80):
        try:
            requests.get(f'http://127.0.0.1:{port}/_log', timeout=0.5); break
        except requests.RequestException:
            time.sleep(0.1)
    yield f'http://127.0.0.1:{port}'
    server.should_exit = True


@pytest.fixture
def env(mock_base, monkeypatch, tmp_path):
    from dev_tools import mock_providers
    mock_providers.TT_STATE.update(privacy_options=['PUBLIC_TO_EVERYONE', 'MUTUAL_FOLLOW_FRIENDS',
                                                    'FOLLOWER_OF_CREATOR', 'SELF_ONLY'],
                                   comment_disabled=False, duet_disabled=False, stitch_disabled=False,
                                   max_duration_sec=600, fail_publish=False)
    monkeypatch.setenv('TIKTOK_AUTH_BASE', mock_base + '/tiktok')
    monkeypatch.setenv('TIKTOK_API_BASE', mock_base + '/tiktok')
    monkeypatch.setenv('TIKTOK_CLIENT_KEY', 'mocktiktokkey')
    monkeypatch.setenv('TIKTOK_CLIENT_SECRET', 'mocktiktoksecret')
    monkeypatch.setenv('PUBLIC_BASE_URL', 'https://studio.test')
    requests.delete(mock_base + '/_log')
    from community_app import create_app
    app = create_app(tmp_path, secret_key=KEY)
    return app, mock_base, tmp_path, mock_providers


def signup(c, name='kevin'):
    r = c.post('/api/register', json={'username': name, 'email': f'{name}@ex.com', 'password': 'SecretPass12345'})
    assert r.status_code == 200, r.text
    return {'X-CSRF-Token': r.json()['csrf']}


def approve(auth_url):
    page = requests.get(auth_url).text
    return _html.unescape(re.search(r'id="approve" href="([^"]+)"', page).group(1))


def connect_tiktok(c, h):
    url = c.post('/api/connectors/tiktok/start', headers=h).json()['auth_url']
    u = urlsplit(approve(url))
    r = c.get(u.path + '?' + u.query, follow_redirects=False)
    assert r.status_code == 303, r.text
    return r.headers['location']


def calls(mock_base, kind):
    return [x for x in requests.get(mock_base + '/_log').json()['calls'] if x['kind'] == kind]


def make_clip(tmp_path, user_id, project_id, data=b'\x00\x00\x00\x18ftypmp42' + b'x' * 4000):
    """Stand in for a finished studio clip: the preview file the project points at."""
    d = tmp_path / 'videos' / str(user_id)
    d.mkdir(parents=True, exist_ok=True)
    f = d / f'studio_{project_id}.mp4'
    f.write_bytes(data)
    db = sqlite3.connect(tmp_path / 'community.db')
    db.execute('UPDATE studio_projects SET preview_file=? WHERE id=?', (f.name, project_id))
    db.commit(); db.close()
    return f


def new_project(c, h):
    b = c.get('/api/studio/bootstrap').json()
    return c.post('/api/studio/projects', headers=h,
                  json={'product_id': b['products'][0]['id'], 'style': 'ugc_pov'}).json()['project']['id']


# ----------------------------------------------------------------------- OAuth
def test_oauth_connects_account_and_reports_ready(env):
    app, mock, _, _ = env
    c = TestClient(app); h = signup(c)
    cfgs = c.get('/api/connectors').json()['config']
    assert cfgs['tiktok']['ready'] is True
    assert cfgs['tiktok']['redirect_uri'] == 'https://studio.test/api/oauth/tiktok/callback'

    assert c.post('/api/connectors/tiktok/start').status_code == 403  # CSRF guard
    url = c.post('/api/connectors/tiktok/start', headers=h).json()['auth_url']
    assert '/tiktok/v2/auth/authorize/' in url and 'video.publish' in url and 'response_type=code' in url

    loc = connect_tiktok(c, h)
    assert 'oauth=success' in loc and 'platform=tiktok' in loc
    ch = [x for x in c.get('/api/connectors').json()['channels'] if x['platform'] == 'tiktok'][0]
    assert ch['account_name'] == '@candelaz.kengza' and ch['kind'] == 'oauth' and ch['has_token']
    assert ch['meta']['followers'] == 1280
    assert calls(mock, 'tiktok.token')[0]['redirect_uri'] == 'https://studio.test/api/oauth/tiktok/callback'


def test_oauth_denied_and_state_replay_are_rejected(env):
    app, _, _, _ = env
    c = TestClient(app); h = signup(c)
    url = c.post('/api/connectors/tiktok/start', headers=h).json()['auth_url']
    state = re.search(r'state=([^&]+)', url).group(1)
    r = c.get('/api/oauth/tiktok/callback', params={'state': state, 'error': 'access_denied'}, follow_redirects=False)
    loc = unquote(r.headers['location'])
    assert 'oauth=error' in loc and 'คุณกดยกเลิกการอนุญาต' in loc
    # the state is single-use, so an attacker replaying the same callback gets nothing
    url2 = c.post('/api/connectors/tiktok/start', headers=h).json()['auth_url']
    u = urlsplit(approve(url2))
    assert c.get(u.path + '?' + u.query, follow_redirects=False).status_code == 303
    again = c.get(u.path + '?' + u.query, follow_redirects=False)
    assert 'oauth=error' in again.headers['location']
    assert not [x for x in c.get('/api/connectors').json()['channels'] if x['platform'] == 'tiktok'][1:]


def test_verify_refreshes_expired_token_and_reports_creator_options(env):
    app, mock, tmp_path, _ = env
    c = TestClient(app); h = signup(c)
    connect_tiktok(c, h)
    ch = [x for x in c.get('/api/connectors').json()['channels'] if x['platform'] == 'tiktok'][0]
    db = sqlite3.connect(tmp_path / 'community.db')
    db.execute("UPDATE connected_channels SET token_expires_at='2020-01-01T00:00:00+00:00' WHERE id=?", (ch['id'],))
    db.commit(); db.close()

    r = c.post(f"/api/connectors/{ch['id']}/verify", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()['detail']
    assert d['username'] == 'candelaz.kengza' and d['max_duration_sec'] == 600
    assert 'PUBLIC_TO_EVERYONE' in d['privacy_options']
    assert len(calls(mock, 'tiktok.refresh')) == 1, 'an expired token must be refreshed, not reused'


# ----------------------------------------------------------- Direct Post
def test_direct_post_uploads_clip_and_reaches_publish_complete(env):
    app, mock, tmp_path, _ = env
    c = TestClient(app); h = signup(c)
    connect_tiktok(c, h)
    ch = [x for x in c.get('/api/connectors').json()['channels'] if x['platform'] == 'tiktok'][0]
    pid = new_project(c, h)
    clip = make_clip(tmp_path, 1, pid)

    info = c.get(f"/api/connectors/{ch['id']}/tiktok/creator-info", headers=h).json()
    assert info['nickname'] == 'Candelaz Kengza' and info['audited'] is True
    assert set(info['privacy_labels']) == set(info['privacy_options'])

    r = c.post(f"/api/connectors/{ch['id']}/tiktok/post", headers=h, json={
        'project_id': pid, 'title': 'รีวิวของดีบอกต่อ #ShopeeAffiliate',
        'privacy_level': 'PUBLIC_TO_EVERYONE', 'brand_content_toggle': True,
        'is_aigc': True, 'agreed_music_terms': True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['ok'] and body['publish_id'].startswith('v_pub_')
    assert body['uploaded_bytes'] == clip.stat().st_size

    init = calls(mock, 'tiktok.init')[-1]
    assert init['privacy'] == 'PUBLIC_TO_EVERYONE' and init['is_aigc'] is True
    assert init['brand_content'] is True and init['chunks'] == 1
    assert 'ShopeeAffiliate' in init['title']
    up = calls(mock, 'tiktok.upload')[-1]
    assert up['range'] == f'bytes 0-{clip.stat().st_size - 1}/{clip.stat().st_size}'

    seen = []
    for _ in range(6):
        st = c.get(f"/api/connectors/{ch['id']}/tiktok/status",
                   headers=h, params={'publish_id': body['publish_id']}).json()
        seen.append(st['status'])
        if st['done']:
            break
    assert seen[-1] == 'PUBLISH_COMPLETE'
    assert st['post_url'] == 'https://www.tiktok.com/@candelaz.kengza/video/7300000000000000001'


def test_unaudited_account_is_held_to_self_only(env):
    """An unaudited client only ever sees SELF_ONLY, and TikTok forbids pairing that with
    a branded-content declaration — the API must refuse that combination, not paper over it."""
    app, _, tmp_path, mp = env
    mp.TT_STATE['privacy_options'] = ['SELF_ONLY']
    c = TestClient(app); h = signup(c)
    connect_tiktok(c, h)
    ch = [x for x in c.get('/api/connectors').json()['channels'] if x['platform'] == 'tiktok'][0]
    pid = new_project(c, h); make_clip(tmp_path, 1, pid)

    info = c.get(f"/api/connectors/{ch['id']}/tiktok/creator-info", headers=h).json()
    assert info['privacy_options'] == ['SELF_ONLY'] and info['audited'] is False

    pub = c.post(f"/api/connectors/{ch['id']}/tiktok/post", headers=h, json={
        'project_id': pid, 'privacy_level': 'PUBLIC_TO_EVERYONE', 'agreed_music_terms': True})
    assert pub.status_code == 400 and 'ความเป็นส่วนตัว' in pub.json()['detail']

    clash = c.post(f"/api/connectors/{ch['id']}/tiktok/post", headers=h, json={
        'project_id': pid, 'privacy_level': 'SELF_ONLY',
        'brand_content_toggle': True, 'agreed_music_terms': True})
    assert clash.status_code == 502 and 'Branded content' in clash.json()['detail']

    ok = c.post(f"/api/connectors/{ch['id']}/tiktok/post", headers=h, json={
        'project_id': pid, 'privacy_level': 'SELF_ONLY', 'agreed_music_terms': True})
    assert ok.status_code == 200 and ok.json()['privacy_level'] == 'SELF_ONLY'


def test_account_level_locks_and_music_terms_are_enforced(env):
    app, _, tmp_path, mp = env
    mp.TT_STATE.update(comment_disabled=True, duet_disabled=True)
    c = TestClient(app); h = signup(c)
    connect_tiktok(c, h)
    ch = [x for x in c.get('/api/connectors').json()['channels'] if x['platform'] == 'tiktok'][0]
    pid = new_project(c, h); make_clip(tmp_path, 1, pid)
    base = {'project_id': pid, 'privacy_level': 'SELF_ONLY'}

    no_terms = c.post(f"/api/connectors/{ch['id']}/tiktok/post", headers=h, json={**base, 'agreed_music_terms': False})
    assert no_terms.status_code == 400 and 'เพลง' in no_terms.json()['detail']

    r = c.post(f"/api/connectors/{ch['id']}/tiktok/post", headers=h, json={**base, 'agreed_music_terms': True})
    assert r.status_code == 400 and 'คอมเมนต์' in r.json()['detail']

    r2 = c.post(f"/api/connectors/{ch['id']}/tiktok/post", headers=h,
                json={**base, 'agreed_music_terms': True, 'disable_comment': True})
    assert r2.status_code == 400 and 'Duet' in r2.json()['detail']

    ok = c.post(f"/api/connectors/{ch['id']}/tiktok/post", headers=h,
                json={**base, 'agreed_music_terms': True, 'disable_comment': True, 'disable_duet': True})
    assert ok.status_code == 200


def test_post_needs_a_clip_and_a_channel_you_own(env):
    app, _, tmp_path, _ = env
    c = TestClient(app); h = signup(c)
    connect_tiktok(c, h)
    ch = [x for x in c.get('/api/connectors').json()['channels'] if x['platform'] == 'tiktok'][0]
    pid = new_project(c, h)   # no clip rendered yet
    r = c.post(f"/api/connectors/{ch['id']}/tiktok/post", headers=h,
               json={'project_id': pid, 'privacy_level': 'SELF_ONLY', 'agreed_music_terms': True})
    assert r.status_code == 409 and 'ยังไม่มีไฟล์คลิป' in r.json()['detail']

    other = TestClient(app); ho = signup(other, 'mallory')
    assert other.get(f"/api/connectors/{ch['id']}/tiktok/creator-info", headers=ho).status_code == 404
    assert other.post(f"/api/connectors/{ch['id']}/tiktok/post", headers=ho,
                      json={'project_id': pid, 'agreed_music_terms': True}).status_code == 404


def test_failed_publish_surfaces_the_reason(env):
    app, _, tmp_path, mp = env
    mp.TT_STATE['fail_publish'] = True
    c = TestClient(app); h = signup(c)
    connect_tiktok(c, h)
    ch = [x for x in c.get('/api/connectors').json()['channels'] if x['platform'] == 'tiktok'][0]
    pid = new_project(c, h); make_clip(tmp_path, 1, pid)
    body = c.post(f"/api/connectors/{ch['id']}/tiktok/post", headers=h, json={
        'project_id': pid, 'privacy_level': 'SELF_ONLY', 'agreed_music_terms': True}).json()
    st = c.get(f"/api/connectors/{ch['id']}/tiktok/status", headers=h,
               params={'publish_id': body['publish_id']}).json()
    assert st['status'] == 'FAILED' and st['fail_reason'] == 'file_format_check_failed'
    assert st['done'] is True and st['post_url'] == ''


def test_disconnect_revokes_the_grant_with_tiktok(env):
    app, mock, _, _ = env
    c = TestClient(app); h = signup(c)
    connect_tiktok(c, h)
    ch = [x for x in c.get('/api/connectors').json()['channels'] if x['platform'] == 'tiktok'][0]
    assert c.delete(f"/api/connectors/{ch['id']}", headers=h).status_code == 200
    assert len(calls(mock, 'tiktok.revoke')) == 1
    assert not [x for x in c.get('/api/connectors').json()['channels'] if x['platform'] == 'tiktok']


def test_chunk_plan_splits_large_files_only(env):
    from integrations import tiktok
    assert tiktok.plan_chunks(4000) == (4000, 1)
    assert tiktok.plan_chunks(60 * 1024 * 1024) == (60 * 1024 * 1024, 1)
    size = 300 * 1024 * 1024
    chunk, count = tiktok.plan_chunks(size)
    assert chunk == 10 * 1024 * 1024 and count == 30
    with pytest.raises(tiktok.TikTokError):
        tiktok.plan_chunks(5 * 1024 * 1024 * 1024)
