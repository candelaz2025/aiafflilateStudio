"""Demo mode: visitors get a private account without signing up; signing up keeps their work."""
import sqlite3
from fastapi.testclient import TestClient

KEY = b'HCMiHM3FNUmDDvPGmUKpkTMKyvIWUZSdLHvufz1qUdc='


def _app(tmp_path):
    from community_app import create_app
    return create_app(tmp_path, secret_key=KEY)


def test_demo_start_upgrade_keeps_work(tmp_path):
    app = _app(tmp_path)
    c = TestClient(app)
    d = c.post('/api/demo/start').json()
    assert d['is_demo'] is True and d['username'].startswith('demo_') and d['reused'] is False
    h = {'X-CSRF-Token': d['csrf']}
    me = c.get('/api/me').json()
    assert me['is_demo'] is True and me['credits'] == 50
    # same browser → same demo account
    assert c.post('/api/demo/start').json()['reused'] is True
    # demo can do real work
    b = c.get('/api/studio/bootstrap').json()
    assert len(b['products']) == 1
    r = c.post('/api/my/products/manual', headers=h, data={'title': 'แก้วเก็บความเย็น 30oz', 'price': '259', 'commission_rate': '8'})
    assert r.status_code == 200, r.text
    # demo accounts do not use beta seats
    assert c.get('/api/beta/capacity').json()['registered'] == 0
    # sign up from the demo session → same user id, work kept
    db = sqlite3.connect(tmp_path / 'community.db')
    demo_id = db.execute('SELECT id FROM users WHERE is_demo=1').fetchone()[0]
    r = c.post('/api/register', json={'username': 'realuser', 'email': 'real@ex.com', 'password': 'SecretPass12345'})
    assert r.status_code == 200, r.text
    me = c.get('/api/me').json()
    assert me['id'] == demo_id and me['is_demo'] is False and me['username'] == 'realuser'
    assert db.execute('SELECT COUNT(*) FROM products WHERE user_id=?', (demo_id,)).fetchone()[0] == 2
    assert c.get('/api/beta/capacity').json()['registered'] == 1


def test_demo_isolated_per_browser_and_rate_limited(tmp_path, monkeypatch):
    import community_app
    monkeypatch.setattr(community_app, 'DEMO_PER_IP_HOUR', 2)
    app = _app(tmp_path)
    a, b = TestClient(app), TestClient(app)
    ua = a.post('/api/demo/start').json()['username']
    ub = b.post('/api/demo/start').json()['username']
    assert ua != ub
    assert TestClient(app).post('/api/demo/start').status_code == 429


def test_real_session_is_not_replaced(tmp_path):
    c = TestClient(_app(tmp_path))
    c.post('/api/register', json={'username': 'kevin', 'email': 'k@ex.com', 'password': 'SecretPass12345'})
    r = c.post('/api/demo/start').json()
    assert r['reused'] is True and r['is_demo'] is False and r['username'] == 'kevin'
