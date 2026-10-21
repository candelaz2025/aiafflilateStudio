"""Phase 1 Studio flow: sample seed → UGC script → preview upload → AI clip (credits charge/refund) → TikTok queue."""
import sqlite3
import pytest
from fastapi.testclient import TestClient

KEY = b'HCMiHM3FNUmDDvPGmUKpkTMKyvIWUZSdLHvufz1qUdc='


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('VIDEO_MOCK', '1')
    monkeypatch.setenv('VIDEO_MOCK_SECONDS', '0')
    monkeypatch.setenv('STUDIO_CLIP_CREDITS', '10')
    from community_app import create_app
    app = create_app(tmp_path, secret_key=KEY)
    c = TestClient(app)
    r = c.post('/api/register', json={'username': 'kevin', 'email': 'k@ex.com', 'password': 'SecretPass12345'})
    return c, {'X-CSRF-Token': r.json()['csrf']}, tmp_path


def test_seed_and_full_flow(client):
    c, h, tmp = client
    b = c.get('/api/studio/bootstrap').json()
    assert len(b['products']) == 1 and b['products'][0]['source'] == 'sample'
    assert b['projects'][0]['status'] == 'script_ready' and b['projects'][0]['is_sample'] == 1
    assert len(b['styles']) == 6 and b['platforms']['tiktok']['connected'] is False
    assert b['engine']['mode'] == 'simulate' and b['engine']['cost_credits'] == 10
    # seeding is idempotent, and does not come back after deleting
    assert len(c.get('/api/studio/bootstrap').json()['products']) == 1
    pid = b['products'][0]['id']
    pr = c.post('/api/studio/projects', headers=h, json={'product_id': pid, 'style': 'ugc_3reasons'}).json()['project']
    assert pr['script']['scenes'][1]['text'].startswith('1)') and '#รีวิว' in pr['caption']
    # edit script
    sc = pr['script']; sc['scenes'][0]['text'] = 'ฮุคใหม่ของฉัน'
    pr = c.patch(f'/api/studio/projects/{pr["id"]}', headers=h, json={'script': sc, 'caption': 'แคปชั่นใหม่ #tiktok'}).json()['project']
    assert pr['script']['hook'] == 'ฮุคใหม่ของฉัน' and pr['caption'] == 'แคปชั่นใหม่ #tiktok'
    # cannot queue before a clip exists
    assert c.post(f'/api/studio/projects/{pr["id"]}/save?target=tiktok_queue', headers=h).status_code == 409
    webm = b'\x1aE\xdf\xa3' + b'\x00' * 200
    up = c.post(f'/api/studio/projects/{pr["id"]}/preview', headers=h, files={'file': ('p.webm', webm, 'video/webm')})
    assert up.status_code == 200 and up.json()['project']['status'] == 'preview_ready'
    assert c.get(up.json()['project']['preview_url']).content == webm
    assert c.post(f'/api/studio/projects/{pr["id"]}/preview', headers=h, files={'file': ('p.webm', b'nope', 'video/webm')}).status_code == 400
    # AI clip: charges 10 credits, finishes, file served
    before = c.get('/api/me').json()['credits']
    r = c.post(f'/api/studio/projects/{pr["id"]}/ai-clip', headers=h).json()
    assert r['project']['status'] == 'clip_running' and r['credits'] == before - 10
    r = c.post(f'/api/studio/projects/{pr["id"]}/ai-clip/refresh', headers=h).json()
    assert r['project']['status'] == 'clip_ready' and r['project']['clip_url']
    assert c.get(r['project']['clip_url']).status_code == 200
    q = c.post(f'/api/studio/projects/{pr["id"]}/save?target=tiktok_queue', headers=h)
    assert q.status_code == 200 and q.json()['project']['status'] == 'queued_tiktok'
    c.post(f'/api/studio/projects/{pr["id"]}/save?target=tiktok_queue', headers=h)
    assert len([x for x in c.get('/api/my/queue').json() if x['platform'] == 'tiktok']) == 1
    ledger = c.get('/api/studio/credits').json()['ledger']
    assert ledger[0]['delta'] == -10


def test_failure_refund_and_insufficient(client):
    c, h, tmp = client
    b = c.get('/api/studio/bootstrap').json()
    p = b['projects'][0]
    sc = p['script']; sc['scenes'][0]['text'] = 'MOCK_FAIL test'
    c.patch(f'/api/studio/projects/{p["id"]}', headers=h, json={'script': sc})
    before = c.get('/api/me').json()['credits']
    c.post(f'/api/studio/projects/{p["id"]}/ai-clip', headers=h)
    r = c.post(f'/api/studio/projects/{p["id"]}/ai-clip/refresh', headers=h).json()
    assert r['project']['status'] == 'clip_failed' and r['project']['credits_refunded'] == 1
    assert r['credits'] == before
    assert any(x['delta'] == 10 and x['reason'].startswith('refund') for x in c.get('/api/studio/credits').json()['ledger'])
    db = sqlite3.connect(tmp / 'community.db'); db.execute('UPDATE users SET credits=3'); db.commit(); db.close()
    r = c.post(f'/api/studio/projects/{p["id"]}/ai-clip', headers=h)
    assert r.status_code == 402 and 'เครดิตไม่พอ' in r.json()['detail']


def test_quick_product_and_isolation(client, tmp_path):
    c, h, tmp = client
    r = c.post('/api/studio/quick-product', headers=h, json={'title': 'แก้วเก็บความเย็น 30oz', 'platform': 'shopee'}).json()
    assert r['reused'] is False
    assert c.post('/api/studio/quick-product', headers=h, json={'title': 'แก้วเก็บความเย็น 30oz'}).json()['id'] == r['id']
    other = TestClient(c.app)
    ho = {'X-CSRF-Token': other.post('/api/register', json={'username': 'eve', 'email': 'e@ex.com', 'password': 'SecretPass12345'}).json()['csrf']}
    assert other.post('/api/studio/projects', headers=ho, json={'product_id': r['id'], 'style': 'ugc_pov'}).status_code == 404
    assert c.get('/api/studio/bootstrap').json()['projects'] == []  # had a product already -> no sample seeded
    mine = c.post('/api/studio/projects', headers=h, json={'product_id': r['id'], 'style': 'ugc_pov'}).json()['project']['id']
    assert other.get(f'/api/studio/projects/{mine}').status_code == 404
    assert c.post('/api/studio/projects', headers=h, json={'product_id': r['id'], 'style': 'ugc_hack'}).status_code == 400
