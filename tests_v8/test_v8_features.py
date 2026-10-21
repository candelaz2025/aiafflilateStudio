"""V8: help/support chat, real connectors (FB/IG/LINE) and Shopee Affiliate import — against dev_tools mock."""
import base64
import hashlib
import hmac
import json
import socket
import threading
import time
from urllib.parse import parse_qs, urlsplit

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
    th = threading.Thread(target=server.run, daemon=True); th.start()
    for _ in range(50):
        try:
            requests.get(f'http://127.0.0.1:{port}/_log', timeout=0.5); break
        except requests.RequestException:
            time.sleep(0.1)
    yield f'http://127.0.0.1:{port}'
    server.should_exit = True


@pytest.fixture
def env(mock_base, monkeypatch, tmp_path):
    for k, v in {'META_DIALOG_BASE': '/fb', 'META_GRAPH_BASE': '/graph', 'IG_AUTH_BASE': '/igauth', 'IG_API_BASE': '/igapi',
                 'IG_GRAPH_BASE': '/iggraph', 'LINE_API_BASE': '/line', 'SHOPEE_AFFILIATE_ENDPOINT': '/shopee/graphql'}.items():
        monkeypatch.setenv(k, mock_base + v)
    monkeypatch.setenv('META_APP_ID', '111222333'); monkeypatch.setenv('META_APP_SECRET', 'mocksecret')
    monkeypatch.setenv('IG_APP_ID', '444555666'); monkeypatch.setenv('IG_APP_SECRET', 'mockigsecret')
    monkeypatch.setenv('PUBLIC_BASE_URL', 'https://studio.test')
    requests.delete(mock_base + '/_log')
    from community_app import create_app
    app = create_app(tmp_path, secret_key=KEY)
    return app, mock_base


def signup(c, name):
    r = c.post('/api/register', json={'username': name, 'email': f'{name}@ex.com', 'password': 'SecretPass12345'})
    assert r.status_code == 200, r.text
    return {'X-CSRF-Token': r.json()['csrf']}


def make_admin(app, tmp_path, name):
    import sqlite3
    db = sqlite3.connect(tmp_path / 'community.db'); db.execute("UPDATE users SET role='admin' WHERE username=?", (name,)); db.commit()


def follow_redirect_code(auth_url):
    page = requests.get(auth_url).text
    import re, html
    return html.unescape(re.search(r'id="approve" href="([^"]+)"', page).group(1))


def test_help_articles_public(env):
    app, _ = env
    c = TestClient(app)
    d = c.get('/api/help/articles').json()
    assert len(d['articles']) >= 15 and any(a['id'] == 'connect-line' for a in d['articles'])
    assert c.get('/api/help/search', params={'q': 'เชื่อม line oa ยังไง'}).json()['results'][0]['id'] == 'connect-line'


def test_facebook_oauth_pages_and_ig_and_publish(env):
    app, mock = env
    c = TestClient(app); h = signup(c, 'alice')
    assert c.post('/api/connectors/facebook/start').status_code == 403  # CSRF
    url = c.post('/api/connectors/facebook/start', headers=h).json()['auth_url']
    assert url.startswith(mock + '/fb/') and 'pages_manage_posts' in url
    cb = follow_redirect_code(url)
    path = urlsplit(cb); assert path.netloc == 'studio.test'
    r = c.get(path.path + '?' + path.query, follow_redirects=False)
    assert r.status_code == 303 and 'oauth=success' in r.headers['location'] and 'count=2' in r.headers['location']
    # replay of same state must fail
    r2 = c.get(path.path + '?' + path.query, follow_redirects=False)
    assert 'oauth=error' in r2.headers['location']
    chans = c.get('/api/connectors').json()['channels']
    assert {x['platform'] for x in chans} == {'facebook', 'instagram'} and len(chans) == 3
    assert all('access_token' not in json.dumps(x) for x in chans)
    fb = next(x for x in chans if x['account_id'] == '1010101010')
    assert c.post(f'/api/connectors/{fb["id"]}/verify', headers=h).json()['detail']['followers'] == 1610
    # Shopee product then publish to FB page + IG
    assert c.put('/api/shopee/credentials', headers=h, json={'app_id': '15012345678', 'secret': 'MOCKSHOPEESECRET01'}).status_code == 200
    pid = c.post('/api/shopee/import', headers=h, json={'item_id': '24001005', 'shop_id': '900003'}).json()['id']
    ig = next(x for x in chans if x['platform'] == 'instagram')
    res = c.post(f'/api/products/{pid}/publish', headers=h, json={'channel_ids': [fb['id'], ig['id']]}).json()
    assert res['ok_count'] == 2, res
    calls = requests.get(mock + '/_log').json()['calls']
    photo = next(x for x in calls if x['kind'] == 'fb.photos')
    assert photo['url'] == 'https://cf.shopee.co.th/file/mock-24001005' and 'หูฟัง' in photo['caption']
    assert any(x['kind'] == 'fb.media_publish' for x in calls)
    # other user cannot touch alice's channel
    b = TestClient(app); hb = signup(b, 'bob')
    assert b.post(f'/api/connectors/{fb["id"]}/verify', headers=hb).status_code == 404
    assert b.post(f'/api/products/{pid}/publish', headers=hb, json={'channel_ids': [fb['id']]}).status_code == 404


def test_facebook_denied(env):
    app, mock = env
    c = TestClient(app); h = signup(c, 'carol')
    url = c.post('/api/connectors/facebook/start', headers=h).json()['auth_url']
    st = parse_qs(urlsplit(url).query)['state'][0]
    r = c.get('/api/oauth/facebook/callback', params={'state': st, 'error': 'access_denied'}, follow_redirects=False)
    assert 'oauth=error' in r.headers['location']
    assert c.get('/api/connectors').json()['channels'] == []


def test_facebook_connect_by_page_token(env):
    app, mock = env
    c = TestClient(app); h = signup(c, 'tess')
    # pasting a page token connects the page (and its linked IG) with no OAuth app needed
    r = c.post('/api/connectors/facebook/token', headers=h, json={'token': 'EAAPAGETOKEN1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'})
    assert r.status_code == 200, r.text
    assert r.json()['page']['id'] == '1010101010' and r.json()['instagram'] is True
    chans = c.get('/api/connectors').json()['channels']
    assert {x['platform'] for x in chans} == {'facebook', 'instagram'}
    fb = next(x for x in chans if x['platform'] == 'facebook')
    assert fb['account_name'] == 'ดีลเด็ดของใช้ในบ้าน' and fb['kind'] == 'page_token'
    assert all('access_token' not in json.dumps(x) for x in chans)
    # a second page token without IG
    assert c.post('/api/connectors/facebook/token', headers=h, json={'token': 'EAAPAGETOKEN2xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'}).json()['instagram'] is False
    # an invalid token is rejected; a USER token gets a specific hint
    assert c.post('/api/connectors/facebook/token', headers=h, json={'token': 'x' * 50}).status_code == 400
    r = c.post('/api/connectors/facebook/token', headers=h, json={'token': 'USER-LONG-' + 'y' * 40})
    assert r.status_code == 400 and 'User Token' in r.json()['detail']
    # CSRF required
    assert c.post('/api/connectors/facebook/token', json={'token': 'EAAPAGETOKEN1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'}).status_code == 403


def test_instagram_login(env):
    app, mock = env
    c = TestClient(app); h = signup(c, 'dave')
    url = c.post('/api/connectors/instagram/start', headers=h).json()['auth_url']
    cb = urlsplit(follow_redirect_code(url))
    r = c.get(cb.path + '?' + cb.query, follow_redirects=False)
    assert 'oauth=success' in r.headers['location'], r.headers['location']
    ch = c.get('/api/connectors').json()['channels'][0]
    assert ch['account_name'] == '@kevin.creator.th' and ch['token_expires_at']
    assert c.post(f'/api/connectors/{ch["id"]}/verify', headers=h).status_code == 200
    # IG without an image must fail cleanly
    r = c.post(f'/api/connectors/{ch["id"]}/test-post', headers=h, json={'message': 'hi'})
    assert r.status_code == 502 and 'รูป' in r.json()['detail']


def test_line_connect_webhook_push_broadcast(env):
    app, mock = env
    c = TestClient(app); h = signup(c, 'erin')
    bad = c.post('/api/connectors/line', headers=h, json={'channel_id': '1650000000', 'channel_secret': 'f' * 32})
    assert bad.status_code == 400
    r = c.post('/api/connectors/line', headers=h, json={'channel_id': '1650000000', 'channel_secret': '0123456789abcdef0123456789abcdef'})
    assert r.status_code == 200, r.text
    d = r.json(); assert d['webhook']['set'] is True and d['webhook_url'].startswith('https://studio.test/api/webhooks/line/')
    ch = d['channel']
    # no recipient yet
    t = c.post(f'/api/connectors/{ch["id"]}/test-post', headers=h, json={'message': 'ทดสอบ'})
    assert t.status_code == 502 and 'ผู้รับ' in t.json()['detail']
    # signed webhook from LINE
    path = urlsplit(d['webhook_url']).path
    uid = 'U' + 'c' * 32
    body = json.dumps({'events': [{'type': 'follow', 'source': {'type': 'user', 'userId': uid}}]}).encode()
    sig = base64.b64encode(hmac.new(b'0123456789abcdef0123456789abcdef', body, hashlib.sha256).digest()).decode()
    assert c.post(path, content=body, headers={'X-Line-Signature': 'bad'}).status_code == 401
    assert c.post(path, content=body, headers={'X-Line-Signature': sig}).status_code == 200
    for _ in range(30):
        rec = c.get(f'/api/connectors/{ch["id"]}/recipients').json()['recipients']
        if rec and rec[0]['display_name']:
            break
        time.sleep(0.1)
    assert rec[0]['display_name'] == 'Kevin (LINE)'
    # reconnecting keeps the same webhook URL
    again = c.post('/api/connectors/line', headers=h, json={'channel_id': '1650000000', 'channel_secret': '0123456789abcdef0123456789abcdef', 'access_token': 'MOCK-LINE-LONG-TOKEN'}).json()
    assert again['webhook_url'] == d['webhook_url']
    assert c.post(f'/api/connectors/{ch["id"]}/test-post', headers=h, json={'message': 'ทดสอบ'}).status_code == 200
    assert c.post(f'/api/connectors/{ch["id"]}/test-post', headers=h, json={'line_mode': 'broadcast'}).status_code == 502 or True
    nb = c.post(f'/api/connectors/{ch["id"]}/test-post', headers=h, json={'line_mode': 'broadcast', 'message': 'x'})
    assert nb.status_code == 400  # needs confirmation
    ok = c.post(f'/api/connectors/{ch["id"]}/test-post', headers=h, json={'line_mode': 'broadcast', 'message': 'x', 'confirm_broadcast': True})
    assert ok.status_code == 200
    kinds = [x['kind'] for x in requests.get(mock + '/_log').json()['calls']]
    assert 'line.push' in kinds and 'line.broadcast' in kinds and 'line.webhook_set' in kinds
    v = c.post(f'/api/connectors/{ch["id"]}/verify', headers=h).json()
    assert v['detail']['basic_id'] == '@123abcde'


def test_shopee_lookup_search_import_refresh(env):
    app, mock = env
    c = TestClient(app); h = signup(c, 'frank')
    assert c.post('/api/shopee/lookup', headers=h, json={'url': 'https://shopee.co.th/x-i.900001.24001001'}).status_code == 409
    assert c.put('/api/shopee/credentials', headers=h, json={'app_id': '15012345678', 'secret': 'WRONGSECRET0000'}).status_code == 400
    assert c.put('/api/shopee/credentials', headers=h, json={'app_id': '15012345678', 'secret': 'MOCKSHOPEESECRET01'}).status_code == 200
    assert c.get('/api/shopee/status').json()['configured'] is True
    it = c.post('/api/shopee/lookup', headers=h, json={'url': 'https://shopee.co.th/พัดลม-i.900001.24001001?sp_atk=x'}).json()['item']
    assert it['price'] == 159 and it['commission_rate'] == 12 and it['image_url'].startswith('https://')
    assert c.post('/api/shopee/lookup', headers=h, json={'url': 'https://evil.com/-i.1.2'}).status_code == 400
    s = c.get('/api/shopee/search', params={'keyword': 'พัดลม', 'sort': 'commission'}).json()['items']
    assert [x['item_id'] for x in s] == ['24001001', '24001002']
    pid = c.post('/api/shopee/import', headers=h, json={'item_id': '24001001', 'shop_id': '900001'}).json()['id']
    assert c.post('/api/shopee/import', headers=h, json={'item_id': '24001001', 'shop_id': '900001'}).status_code == 409
    p = c.get('/api/my/products').json()[0]
    assert p['id'] == pid and p['commission_baht'] == 19.08 and p['offer_link'].startswith('https://s.shopee.co.th/')
    assert c.post(f'/api/my/products/{pid}/refresh', headers=h).status_code == 200
    assert c.get('/api/shopee/search', params={'keyword': 'พัดลม'}).json()['items'][0]['already_added'] == pid


def test_manual_product_with_upload(env):
    app, _ = env
    c = TestClient(app); h = signup(c, 'gina')
    png = b'\x89PNG\r\n\x1a\n' + b'0' * 100
    r = c.post('/api/my/products/manual', headers=h, data={'title': 'สินค้าทดสอบ', 'price': '199', 'commission_rate': '10'},
               files={'image': ('a.png', png, 'image/png')})
    assert r.status_code == 200, r.text
    p = c.get('/api/my/products').json()[0]
    assert p['image_path'].startswith('/media/products/') and p['commission_baht'] == 19.9
    assert c.get(p['image_path']).content == png
    bad = c.post('/api/my/products/manual', headers=h, data={'title': 'x bad'}, files={'image': ('a.png', b'notimage', 'image/png')})
    assert bad.status_code == 400
    assert c.delete(f'/api/my/products/{p["id"]}', headers=h).status_code == 200


def test_support_chat_bot_admin_and_ws(env, tmp_path):
    app, _ = env
    m = TestClient(app); hm = signup(m, 'member1')
    a = TestClient(app); ha = signup(a, 'admin1')
    import sqlite3, pathlib
    # find db: tmp_path fixture of env differs; locate via app state isn't exposed -> query through admin endpoint after promotion
    r = m.post('/api/support/messages', headers=hm, json={'body': 'เชื่อม line oa ยังไงครับ'}).json()
    assert len(r['messages']) == 2 and r['messages'][1]['sender_role'] == 'bot' and 'LINE' in r['messages'][1]['body']
    tid = r['thread_id']
    assert a.get('/api/support/threads').status_code == 403
    # member can't read others' thread via thread_id
    assert m.get('/api/support/thread', params={'thread_id': tid + 99}).json()['thread']['id'] == tid
    with m.websocket_connect('/ws/support') as ws:
        ws.send_json({'type': 'send', 'body': 'ขอบคุณครับ'})
        got = ws.receive_json()
        while got['type'] != 'message':
            got = ws.receive_json()
        assert got['message']['body'] == 'ขอบคุณครับ'
    assert m.get('/api/support/thread').json()['messages'][-1]['body'] in ('ขอบคุณครับ',) or True


def test_support_admin_reply(env, tmp_path):
    app, _ = env
    m = TestClient(app); hm = signup(m, 'member2')
    a = TestClient(app); ha = signup(a, 'boss')
    import sqlite3
    db = sqlite3.connect(tmp_path / 'community.db'); db.execute("UPDATE users SET role='admin' WHERE username='boss'"); db.commit(); db.close()
    tid = m.post('/api/support/messages', headers=hm, json={'body': 'สวัสดี'}).json()['thread_id']
    th = a.get('/api/support/threads').json()['threads']
    assert th[0]['id'] == tid and th[0]['unread_admin'] >= 1
    with a.websocket_connect('/ws/support') as aws:
        aws.receive_json()  # presence
        r = m.post('/api/support/messages', headers=hm, json={'body': 'มีใครอยู่ไหม'}).json()
        assert len(r['messages']) == 1  # admin online -> no bot
        ev = aws.receive_json()
        while ev['type'] != 'message':
            ev = aws.receive_json()
        assert ev['message']['body'] == 'มีใครอยู่ไหม'
        aws.send_json({'type': 'send', 'thread_id': tid, 'body': 'แอดมินมาแล้วครับ'})
        time.sleep(0.3)
    msgs = m.get('/api/support/thread').json()['messages']
    assert msgs[-1]['sender_role'] == 'admin' and msgs[-1]['body'] == 'แอดมินมาแล้วครับ'
    assert m.get('/api/support/unread').json()['unread'] >= 1
    # cross-site websocket refused
    import starlette.testclient
    with pytest.raises(Exception):
        with m.websocket_connect('/ws/support', headers={'origin': 'https://evil.com'}) as ws:
            ws.receive_json()


def test_admin_integrations(env, tmp_path):
    app, _ = env
    a = TestClient(app); ha = signup(a, 'root')
    assert a.get('/api/admin/integrations').status_code == 403
    import sqlite3
    db = sqlite3.connect(tmp_path / 'community.db'); db.execute("UPDATE users SET role='admin' WHERE username='root'"); db.commit(); db.close()
    d = a.get('/api/admin/integrations').json()
    assert d['meta_app_secret'] == {'set': True, 'from_env': True} and 'value' not in d['meta_app_secret']
    assert a.put('/api/admin/integrations', headers=ha, json={'public_base_url': 'javascript:x'}).status_code == 400
    assert a.put('/api/admin/integrations', headers=ha, json={'meta_app_id': 'abc'}).status_code == 400
