"""AI rewrite of product names/descriptions and AI product images, with the user's Gemini key."""
import io
import socket
import threading
import time

import pytest
import requests
import uvicorn
from fastapi.testclient import TestClient

KEY = b'HCMiHM3FNUmDDvPGmUKpkTMKyvIWUZSdLHvufz1qUdc='
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 200


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
    from dev_tools import mock_providers as mp
    mp.IMAGE_STATE.update(fail=False, blocked=False); mp.TEXT_STATE.update(fail=False, empty=False, garbage=False)
    monkeypatch.setenv('GEMINI_API_BASE', mock_base + '/gemini')
    requests.delete(mock_base + '/_log')
    from community_app import create_app
    c = TestClient(create_app(tmp_path, secret_key=KEY))
    r = c.post('/api/register', json={'username': 'kevin', 'email': 'k@ex.com', 'password': 'SecretPass12345'})
    return c, {'X-CSRF-Token': r.json()['csrf']}, mock_base, mp, tmp_path


def add(c, h, title='พัดลมพกพา ไร้ใบพัด ชาร์จ USB', photo=True):
    files = {'image': ('a.png', io.BytesIO(PNG), 'image/png')} if photo else None
    r = c.post('/api/my/products/manual', headers=h, files=files,
               data={'title': title, 'platform': 'shopee', 'price': '399', 'commission_rate': '10'})
    assert r.status_code == 200, r.text
    return r.json()['id']


def run(c, h, **body):
    r = c.post('/api/products/ai', headers=h, json=body)
    assert r.status_code == 200, r.text
    jid = r.json()['job_id']
    for _ in range(100):
        j = c.get(f'/api/products/ai/{jid}').json()
        if j['status'] != 'running':
            return j
        time.sleep(0.05)
    raise AssertionError('AI job never finished')


def prod(c, pid):
    return [p for p in c.get('/api/my/products').json() if p['id'] == pid][0]


def calls(mock, kind):
    return [x for x in requests.get(mock + '/_log').json()['calls'] if x['kind'] == kind]


def connect_key(c, h):
    assert c.put('/api/my/keys/gemini', headers=h, json={'key': 'MOCK-GEMINI-KEY'}).status_code == 200


def test_needs_a_gemini_key(env):
    c, h, *_ = env
    add(c, h)
    r = c.post('/api/products/ai', headers=h, json={'do_text': True})
    assert r.status_code == 409 and 'คีย์ Gemini' in r.json()['detail']


def test_rewrites_title_and_description_and_scrubs_hype(env):
    c, h, mock, *_ = env
    connect_key(c, h)
    pid = add(c, h)
    j = run(c, h, product_ids=[pid], do_text=True)
    assert j['text_done'] == 1 and j['failed'] == 0
    p = prod(c, pid)
    assert '(AI)' in p['title'] and 'ดีที่สุด' not in p['title'], 'banned hype must be scrubbed from the title'
    assert p['description'].startswith('• ') and 'หายทันที' not in p['description']
    assert 'เมื่อใช้' not in p['description'], 'a line built on a banned claim is dropped, not left as a fragment'
    assert p['description'].count('•') == 2
    assert p['can_undo_ai'] == 1
    assert 'พัดลมพกพา' in calls(mock, 'gemini.listing')[-1]['prompt'], 'the real title is what the model works from'


def test_undo_restores_the_original_name(env):
    c, h, *_ = env
    connect_key(c, h)
    pid = add(c, h, title='ชื่อเดิมของร้านค้า ABC')
    run(c, h, product_ids=[pid], do_text=True)
    assert prod(c, pid)['title'] != 'ชื่อเดิมของร้านค้า ABC'
    assert c.post(f'/api/my/products/{pid}/ai-undo', headers=h).status_code == 200
    p = prod(c, pid)
    assert p['title'] == 'ชื่อเดิมของร้านค้า ABC' and p['description'] == '' and p['can_undo_ai'] == 0
    assert c.post(f'/api/my/products/{pid}/ai-undo', headers=h).status_code == 409


def test_image_uses_the_real_photo_as_reference_and_keeps_the_original(env):
    c, h, mock, _, tmp = env
    connect_key(c, h)
    pid = add(c, h, photo=True)
    original = prod(c, pid)['image_path']
    j = run(c, h, product_ids=[pid], do_text=False, do_image=True, image_style='lifestyle')
    assert j['image_done'] == 1, j
    call = calls(mock, 'gemini.image')[-1]
    assert call['has_ref'] is True, 'the real photo must be sent so the product stays the same'
    assert 'identical' in call['prompt'] and 'Thai home' in call['prompt'] and call['aspect'] == '1:1'
    p = prod(c, pid)
    assert p['use_ai_image'] == 1 and p['ai_image_path'].startswith('/media/products/ai_')
    assert p['image_path'] == original, 'the original photo is kept, not replaced'
    assert (tmp / 'media' / 'products' / p['ai_image_path'].rsplit('/', 1)[-1]).read_bytes()[:4] == b'\x89PNG'
    # switching back to the original photo
    assert c.patch(f'/api/my/products/{pid}', headers=h, json={'use_ai_image': False}).status_code == 200
    assert prod(c, pid)['use_ai_image'] == 0


def test_no_photo_is_flagged_as_an_illustration(env):
    c, h, mock, *_ = env
    connect_key(c, h)
    pid = add(c, h, photo=False)
    j = run(c, h, product_ids=[pid], do_text=False, do_image=True)
    assert calls(mock, 'gemini.image')[-1]['has_ref'] is False
    assert any('ภาพประกอบ' in n for n in j['items'][0]['notes'])


def test_whole_library_and_both_jobs_in_one_run(env):
    c, h, *_ = env
    connect_key(c, h)
    ids = [add(c, h, title=f'สินค้าทดสอบหมายเลข {i}') for i in range(3)]
    j = run(c, h, do_text=True, do_image=True)          # no ids = every active product
    assert j['total'] == 3 and j['text_done'] == 3 and j['image_done'] == 3
    assert all(prod(c, i)['ai_image_path'] for i in ids)


def test_only_missing_image_skips_products_that_have_one(env):
    c, h, mock, *_ = env
    connect_key(c, h)
    with_photo, without = add(c, h, photo=True), add(c, h, photo=False)
    run(c, h, product_ids=[with_photo, without], do_text=False, do_image=True, only_missing_image=True)
    assert not prod(c, with_photo)['ai_image_path'] and prod(c, without)['ai_image_path']


def test_quota_stops_the_run_instead_of_failing_every_item(env):
    c, h, _, mp, _ = env
    connect_key(c, h)
    for i in range(4):
        add(c, h, title=f'สินค้าโควต้า {i}')
    mp.IMAGE_STATE['fail'] = True
    j = run(c, h, do_text=False, do_image=True)
    assert 'โควต้า' in j['error'] and j['done'] == 1, 'one quota error is enough to stop'


def test_blocked_image_reports_the_reason(env):
    c, h, _, mp, _ = env
    connect_key(c, h)
    pid = add(c, h)
    mp.IMAGE_STATE['blocked'] = True
    j = run(c, h, product_ids=[pid], do_text=False, do_image=True)
    assert j['failed'] == 1 and 'IMAGE_SAFETY' in ' '.join(j['items'][0]['notes'])


def test_cannot_touch_another_users_products(env):
    c, h, *_ = env
    connect_key(c, h)
    pid = add(c, h)
    from community_app import create_app
    other = TestClient(c.app)
    r = other.post('/api/register', json={'username': 'mal', 'email': 'm@e.com', 'password': 'SecretPass12345'})
    ho = {'X-CSRF-Token': r.json()['csrf']}
    other.put('/api/my/keys/gemini', headers=ho, json={'key': 'MOCK-GEMINI-KEY'})
    r = other.post('/api/products/ai', headers=ho, json={'product_ids': [pid], 'do_text': True})
    assert r.status_code == 400, 'someone else\'s product ids resolve to nothing'
    assert other.post(f'/api/my/products/{pid}/ai-undo', headers=ho).status_code == 404
