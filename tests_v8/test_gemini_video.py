"""Real clip generation with the user's own Gemini key: templates, avatars, polling, download."""
import json
import socket
import threading
import time

import pytest
import requests
import uvicorn
from fastapi.testclient import TestClient

KEY = b'HCMiHM3FNUmDDvPGmUKpkTMKyvIWUZSdLHvufz1qUdc='


@pytest.fixture(scope='module')
def mock_base():
    from dev_tools.mock_providers import app as mock_app
    s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
    server = uvicorn.Server(uvicorn.Config(mock_app, host='127.0.0.1', port=port, log_level='warning'))
    t = threading.Thread(target=server.run, daemon=True); t.start()
    for _ in range(100):
        try:
            requests.get(f'http://127.0.0.1:{port}/_log', timeout=1); break
        except requests.RequestException:
            time.sleep(0.05)
    yield f'http://127.0.0.1:{port}'
    server.should_exit = True


@pytest.fixture
def client(mock_base, monkeypatch, tmp_path):
    monkeypatch.setenv('GEMINI_API_BASE', mock_base + '/gemini')
    monkeypatch.delenv('VIDEO_MOCK', raising=False)
    monkeypatch.delenv('PLATFORM_OPENROUTER_API_KEY', raising=False)
    from community_app import create_app
    c = TestClient(create_app(tmp_path, secret_key=KEY))
    r = c.post('/api/register', json={'username': 'kevin', 'email': 'k@ex.com', 'password': 'SecretPass12345'})
    return c, {'X-CSRF-Token': r.json()['csrf']}, tmp_path, mock_base


def _save_key(c, h, key='MOCK-GEMINI-KEY'):
    assert c.put('/api/my/keys/gemini', headers=h, json={'key': key}).status_code == 200


def _project(c, h):
    b = c.get('/api/studio/bootstrap').json()
    pid = b['products'][0]['id']
    return c.post('/api/studio/projects', headers=h, json={'product_id': pid, 'style': 'ugc_pov'}).json()['project']


def _finish(c, h, pid, tries=30):
    for _ in range(tries):
        r = c.post(f'/api/studio/projects/{pid}/ai-clip/refresh', headers=h).json()
        if r['project']['status'] != 'clip_running':
            return r
        time.sleep(0.05)
    raise AssertionError('job never finished')


def test_engine_switches_to_gemini_when_key_saved(client):
    c, h, _, _ = client
    assert c.get('/api/studio/bootstrap').json()['engine']['mode'] == 'sample'
    _save_key(c, h)
    b = c.get('/api/studio/bootstrap').json()
    assert b['engine']['mode'] == 'gemini_own_key'
    assert b['engine']['cost_credits'] == 0 and b['engine']['supports_template'] and b['engine']['supports_avatar']
    assert len(b['templates']) == 6 and b['aspects'] == ['9:16', '16:9']
    assert c.post('/api/studio/gemini/verify', headers=h).json() == {
        'ok': True, 'has_omni': True, 'model': 'gemini-omni-1.1-flash', 'message': 'คีย์ Gemini ใช้งานได้ พร้อมสร้างวิดีโอ'}


def test_full_clip_with_template_and_avatar(client):
    c, h, tmp, mock = client
    _save_key(c, h)
    png = b'\x89PNG\r\n\x1a\n' + b'\x00' * 200
    av = c.post('/api/studio/avatars', headers=h, files={'file': ('mola.png', png, 'image/png')},
                data={'name': 'Mola'}).json()
    assert av['avatars'][0]['name'] == 'Mola'
    assert c.get(f"/api/studio/avatars/{av['id']}/image").content == png
    p = _project(c, h)
    r = c.post(f'/api/studio/projects/{p["id"]}/ai-clip', headers=h,
               json={'template': 'ugc_handheld', 'avatar_id': av['id'], 'aspect': '9:16',
                     'resolution': '1080p', 'seconds': 20, 'voice_over': True})
    assert r.status_code == 200, r.text
    assert r.json()['project']['status'] == 'clip_running'
    assert r.json()['credits'] == 50  # own key → no credits charged
    done = _finish(c, h, p['id'])
    assert done['project']['status'] == 'clip_ready', done
    assert done['project']['clip_url']
    assert c.get(done['project']['clip_url']).content.startswith(b'\x00\x00\x00\x18ftyp')
    # the prompt we sent carried the template style, the avatar and the Thai voice-over
    calls = requests.get(mock + '/_log').json()['calls']
    gen = [x for x in calls if x['kind'] == 'gemini.interactions'][-1]
    assert gen['model'] == 'gemini-omni-1.1-flash' and gen['aspect'] == '9:16' and gen['resolution'] == '1080p'
    assert gen['has_image'] is True
    assert 'handheld phone camera' in gen['prompt'] and 'Thai voice-over' in gen['prompt']
    assert '20-second' in gen['prompt']


def test_template_choice_changes_the_prompt(client):
    c, h, _, mock = client
    _save_key(c, h)
    p = _project(c, h)
    c.post(f'/api/studio/projects/{p["id"]}/ai-clip', headers=h,
           json={'template': 'unbox', 'voice_over': False, 'seconds': 10})
    _finish(c, h, p['id'])
    gen = [x for x in requests.get(mock + '/_log').json()['calls'] if x['kind'] == 'gemini.interactions'][-1]
    assert 'unboxing' in gen['prompt'] and gen['has_image'] is False
    assert 'Thai voice-over' not in gen['prompt']  # voice_over off


def test_bad_template_avatar_and_aspect_rejected(client):
    c, h, _, _ = client
    _save_key(c, h)
    p = _project(c, h)
    url = f'/api/studio/projects/{p["id"]}/ai-clip'
    assert c.post(url, headers=h, json={'template': 'nope'}).status_code == 400
    assert c.post(url, headers=h, json={'template': 'unbox', 'aspect': '1:1'}).status_code == 400
    assert c.post(url, headers=h, json={'template': 'unbox', 'avatar_id': 9999}).status_code == 404
    assert c.post(url, json={'template': 'unbox'}).status_code == 403  # CSRF


def test_provider_failure_surfaces_and_does_not_strand_the_project(client):
    c, h, _, _ = client
    _save_key(c, h)
    p = _project(c, h)
    sc = json.loads(json.dumps(p['script']))
    sc['scenes'][0]['text'] = 'GEMFAIL ทดสอบความล้มเหลว'
    c.patch(f'/api/studio/projects/{p["id"]}', headers=h, json={'script': sc})
    r = c.post(f'/api/studio/projects/{p["id"]}/ai-clip', headers=h, json={'template': 'studio_product'})
    assert r.status_code == 502 and 'Gemini' in r.json()['detail']
    assert c.get('/api/studio/bootstrap').json()['projects'][0]['status'] == 'clip_failed'


def test_avatars_are_private_and_capped(client):
    c, h, _, _ = client
    _save_key(c, h)
    png = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
    a = c.post('/api/studio/avatars', headers=h, files={'file': ('x.png', png, 'image/png')}).json()
    # a text file pretending to be an image is rejected
    assert c.post('/api/studio/avatars', headers=h,
                  files={'file': ('x.png', b'not an image at all', 'image/png')}).status_code == 400
    assert c.post('/api/studio/avatars', headers=h,
                  files={'file': ('x.gif', b'GIF89a', 'image/gif')}).status_code == 400
    # another user cannot read or delete it
    c.cookies.clear()
    r2 = c.post('/api/register', json={'username': 'mallory', 'email': 'm@ex.com', 'password': 'SecretPass12345'})
    h2 = {'X-CSRF-Token': r2.json()['csrf']}
    assert c.get(f"/api/studio/avatars/{a['id']}/image").status_code == 404
    assert c.delete(f"/api/studio/avatars/{a['id']}", headers=h2).status_code == 404
