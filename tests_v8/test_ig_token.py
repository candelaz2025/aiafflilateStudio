"""Connecting Instagram by pasting a token — both routes (IG token, Page token)."""
import re
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
    for k, v in {'META_DIALOG_BASE': '/fb', 'META_GRAPH_BASE': '/graph', 'IG_AUTH_BASE': '/igauth',
                 'IG_API_BASE': '/igapi', 'IG_GRAPH_BASE': '/iggraph'}.items():
        monkeypatch.setenv(k, mock_base + v)
    monkeypatch.setenv('PUBLIC_BASE_URL', 'https://studio.test')
    from community_app import create_app
    c = TestClient(create_app(tmp_path, secret_key=KEY))
    r = c.post('/api/register', json={'username': 'kevin', 'email': 'k@ex.com', 'password': 'SecretPass12345'})
    return c, {'X-CSRF-Token': r.json()['csrf']}


def igs(c):
    return [x for x in c.get('/api/connectors').json()['channels'] if x['platform'] == 'instagram']


def test_instagram_token_connects_directly(client):
    """An Instagram access token resolves through the IG Graph with no app configured."""
    c, h = client
    assert c.get('/api/connectors').json()['config']['instagram']['ready'] is False
    r = c.post('/api/connectors/instagram/token', headers=h, json={'token': 'IG-LONG-' + 'x' * 40})
    assert r.status_code == 200, r.text
    assert r.json()['via'] == 'instagram' and 'kevin.creator.th' in r.json()['message']
    ch = igs(c)[0]
    assert ch['account_name'] == '@kevin.creator.th' and ch['meta']['via'] == 'instagram'
    assert ch['account_id'] == '17841499999999999' and ch['has_token']


def test_page_token_finds_the_linked_instagram(client):
    """Most people hold a Page token, not an IG one — that must work too, via the page."""
    c, h = client
    r = c.post('/api/connectors/instagram/token', headers=h,
               json={'token': 'EAAPAGETOKEN1' + 'x' * 34})
    assert r.status_code == 200, r.text
    assert r.json()['via'] == 'facebook'
    ch = igs(c)[0]
    assert ch['account_name'] == '@deal_home_th'
    assert ch['meta']['via'] == 'facebook' and ch['meta']['page_name'] == 'ดีลเด็ดของใช้ในบ้าน'


def test_page_without_instagram_says_what_to_fix(client):
    """Page 2 in the mock has no linked IG — the error must name the fix, not just fail."""
    c, h = client
    r = c.post('/api/connectors/instagram/token', headers=h, json={'token': 'EAAPAGETOKEN2' + 'x' * 34})
    assert r.status_code == 400
    d = r.json()['detail']
    assert 'ยังไม่ได้ผูกบัญชี Instagram' in d and 'Business Suite' in d
    assert not igs(c)


def test_garbage_token_is_rejected_without_creating_a_channel(client):
    c, h = client
    r = c.post('/api/connectors/instagram/token', headers=h, json={'token': 'NOTATOKEN' + 'z' * 40})
    assert r.status_code == 400 and 'Instagram access token' in r.json()['detail']
    assert not igs(c)
    assert c.post('/api/connectors/instagram/token', json={'token': 'IG-LONG-' + 'x' * 40}).status_code == 403


def test_reconnecting_updates_the_same_channel(client):
    c, h = client
    tok = 'IG-LONG-' + 'x' * 40
    assert c.post('/api/connectors/instagram/token', headers=h, json={'token': tok}).status_code == 200
    assert c.post('/api/connectors/instagram/token', headers=h, json={'token': tok}).status_code == 200
    assert len(igs(c)) == 1, 'the same IG account must not be added twice'


def test_connected_instagram_verifies_and_publishes(client):
    c, h = client
    c.post('/api/connectors/instagram/token', headers=h, json={'token': 'IG-LONG-' + 'x' * 40})
    ch = igs(c)[0]
    v = c.post(f"/api/connectors/{ch['id']}/verify", headers=h)
    assert v.status_code == 200, v.text
    assert v.json()['detail']['followers'] == 2300
