"""Script writing: never the same clip twice, Gemini when a key is connected, copy rules."""
import socket
import threading
import time

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
def client(mock_base, monkeypatch, tmp_path):
    from dev_tools import mock_providers
    mock_providers.TEXT_STATE.update(fail=False, empty=False, garbage=False)
    monkeypatch.setenv('GEMINI_API_BASE', mock_base + '/gemini')
    monkeypatch.delenv('VIDEO_MOCK', raising=False)
    monkeypatch.delenv('PLATFORM_OPENROUTER_API_KEY', raising=False)
    requests.delete(mock_base + '/_log')
    from community_app import create_app
    c = TestClient(create_app(tmp_path, secret_key=KEY))
    r = c.post('/api/register', json={'username': 'kevin', 'email': 'k@ex.com', 'password': 'SecretPass12345'})
    return c, {'X-CSRF-Token': r.json()['csrf']}, mock_base, mock_providers


def boot(c):
    return c.get('/api/studio/bootstrap').json()


def new_project(c, h, style='ugc_pov'):
    b = boot(c)
    return c.post('/api/studio/projects', headers=h,
                  json={'product_id': b['products'][0]['id'], 'style': style}).json()


def hooks_of(p):
    return p['project']['script']['hook']


# -------------------------------------------------------------- no duplicates
def test_builtin_regenerate_never_repeats(client):
    """Pressing สร้างบทใหม่ must change the clip, not reshuffle the same one."""
    c, h, _, _ = client
    assert boot(c)['writer']['mode'] == 'builtin'
    pid = new_project(c, h)['project']['id']
    seen = set()
    for _ in range(8):
        r = c.patch(f'/api/studio/projects/{pid}', headers=h, json={'regenerate': True}).json()
        sc = r['project']['script']
        sig = (sc['hook'], tuple(s['text'] for s in sc['scenes']))
        assert sig not in seen, f'ได้บทซ้ำ: {sc["hook"]}'
        seen.add(sig)


def test_second_project_for_one_product_opens_differently(client):
    c, h, _, _ = client
    first = new_project(c, h)
    second = new_project(c, h)
    assert hooks_of(first) != hooks_of(second)


# ------------------------------------------------------------------ Gemini
def test_gemini_writes_the_script_when_a_key_is_connected(client):
    c, h, mock, _ = client
    assert c.put('/api/my/keys/gemini', headers=h, json={'key': 'MOCK-GEMINI-KEY'}).status_code == 200
    w = boot(c)['writer']
    assert w['mode'] == 'gemini' and 'ไม่ซ้ำ' in w['label']

    p = new_project(c, h)
    assert p['project']['script']['source'] == 'gemini'
    assert 'จาก Gemini' in hooks_of(p)

    calls = [x for x in requests.get(mock + '/_log').json()['calls'] if x['kind'] == 'gemini.text']
    assert calls, 'the model should have been asked'
    assert 'POV ใช้จริง' in calls[-1]['prompt'], 'the chosen style must reach the model'


def test_regenerate_tells_gemini_what_not_to_repeat(client):
    c, h, mock, _ = client
    c.put('/api/my/keys/gemini', headers=h, json={'key': 'MOCK-GEMINI-KEY'})
    pid = new_project(c, h)['project']['id']
    first = c.get(f'/api/studio/projects/{pid}').json()['project']['script']['hook']
    c.patch(f'/api/studio/projects/{pid}', headers=h, json={'regenerate': True})
    calls = [x for x in requests.get(mock + '/_log').json()['calls'] if x['kind'] == 'gemini.text']
    assert first in calls[-1]['prompt'], 'the previous opener must be sent as something to avoid'
    assert 'ห้ามเขียนให้ซ้ำ' in calls[-1]['prompt']


def test_gemini_failure_falls_back_and_says_so(client):
    c, h, _, mp = client
    c.put('/api/my/keys/gemini', headers=h, json={'key': 'MOCK-GEMINI-KEY'})
    mp.TEXT_STATE['fail'] = True
    r = c.post('/api/studio/projects', headers=h,
               json={'product_id': boot(c)['products'][0]['id'], 'style': 'ugc_pov'}).json()
    assert r['project']['script']['source'] == 'builtin'
    assert 'Gemini ไม่สำเร็จ' in r['notice'] and 'โควต้า' in r['notice']


def test_unreadable_model_output_falls_back_too(client):
    c, h, _, mp = client
    c.put('/api/my/keys/gemini', headers=h, json={'key': 'MOCK-GEMINI-KEY'})
    mp.TEXT_STATE['garbage'] = True
    r = c.post('/api/studio/projects', headers=h,
               json={'product_id': boot(c)['products'][0]['id'], 'style': 'ugc_pov'}).json()
    assert r['project']['script']['source'] == 'builtin' and 'notice' in r


# -------------------------------------------------------------- copy rules
def test_voice_track_is_written_the_way_it_is_read(client):
    """A voice model handed '฿199' reads it wrong; handed Thai words it reads it right."""
    c, h, _, _ = client
    sc = new_project(c, h, 'ugc_budget')['project']['script']
    track = ' '.join(sc['voice_track'])
    assert 'หนึ่งร้อยเก้าสิบเก้าบาท' in track
    assert '฿' not in track and not any(ch.isdigit() for ch in track)


def test_generated_copy_carries_no_banned_claims(client):
    c, h, _, _ = client
    from integrations import copy_rules
    for style in ('ugc_pov', 'ugc_budget', 'ugc_3reasons', 'ugc_problem'):
        sc = new_project(c, h, style)['project']['script']
        blob = ' '.join(s['text'] + ' ' + s['voice'] for s in sc['scenes']) + sc['caption']
        assert not copy_rules.banned_in(blob), f'{style}: {copy_rules.banned_in(blob)}'
        assert len(sc['hashtags'].split()) == copy_rules.HASHTAG_COUNT
        assert len(set(sc['hashtags'].split())) == copy_rules.HASHTAG_COUNT, 'hashtags must not repeat'
        assert len(sc['caption']) <= copy_rules.CAPTION_MAX


def test_script_carries_placement_for_the_video_prompt(client):
    c, h, _, _ = client
    sc = new_project(c, h)['project']['script']
    assert sc['placement']['position'] == 'top-center' and sc['placement']['aspect'] == '9:16'


def test_price_contradiction_is_reported_not_hidden(client):
    from integrations import copy_rules
    bad = {'scenes': [{'t': '0-2s', 'text': 'ถูกมาก', 'voice': 'ราคาแค่ ฿99 เท่านั้น'}], 'caption': ''}
    issues = copy_rules.check(bad, {'price': 199})
    assert any('฿99' in i and '฿199' in i for i in issues)
    assert not copy_rules.check(bad, {'price': 99})
