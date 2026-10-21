"""Auto-Post scheduler against the mock providers: immediate, Facebook-native scheduled, worker tick, cancel, retry."""
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import requests
from fastapi.testclient import TestClient

from tests_v8.test_v8_features import env, follow_redirect_code, mock_base, signup  # noqa: F401  (fixtures)


def setup_user(app, mock, name):
    c = TestClient(app); h = signup(c, name)
    cb = urlsplit(follow_redirect_code(c.post('/api/connectors/facebook/start', headers=h).json()['auth_url']))
    c.get(cb.path + '?' + cb.query, follow_redirects=False)
    chans = c.get('/api/connectors').json()['channels']
    c.put('/api/shopee/credentials', headers=h, json={'app_id': '15012345678', 'secret': 'MOCKSHOPEESECRET01'})
    pid = c.post('/api/shopee/import', headers=h, json={'item_id': '24001005', 'shop_id': '900003'}).json()['id']
    proj = c.post('/api/studio/projects', headers=h, json={'product_id': pid, 'style': 'ugc_pov'}).json()['project']
    c.post(f'/api/studio/projects/{proj["id"]}/preview', headers=h, files={'file': ('p.webm', b'\x1aE\xdf\xa3' + b'0' * 300, 'video/webm')})
    fb = [x for x in chans if x['platform'] == 'facebook']
    ig = next(x for x in chans if x['platform'] == 'instagram')
    return c, h, pid, proj['id'], fb, ig


def calls(mock, kind):
    return [x for x in requests.get(mock + '/_log').json()['calls'] if x['kind'] == kind]


def test_post_now_video_to_facebook_and_image_to_ig(env, monkeypatch):
    monkeypatch.setenv('SCHEDULER_WORKER', '0')
    app, mock = env
    c, h, pid, proj, fb, ig = setup_user(app, mock, 'sched1')
    r = c.post('/api/scheduled-posts', headers=h, json={'product_id': pid, 'project_id': proj, 'channel_ids': [fb[0]['id'], ig['id']],
                                                        'caption': 'รีวิวหูฟัง #ป้ายยา'})
    assert r.status_code == 200, r.text
    post = r.json()['post']
    assert post['status'] == 'posted', post
    v = calls(mock, 'fb.videos')[-1]
    assert v['source'].startswith('<file') and 'รีวิวหูฟัง' in v['description'] and 'published' not in v
    assert calls(mock, 'fb.media_publish')  # IG via page: image (preview is webm, not reels)


def test_future_facebook_uses_native_scheduling_and_cancel(env, monkeypatch):
    monkeypatch.setenv('SCHEDULER_WORKER', '0')
    app, mock = env
    c, h, pid, proj, fb, ig = setup_user(app, mock, 'sched2')
    when = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    post = c.post('/api/scheduled-posts', headers=h, json={'product_id': pid, 'project_id': proj, 'channel_ids': [fb[0]['id']],
                                                           'caption': 'ตั้งเวลา', 'scheduled_at': when}).json()['post']
    assert post['status'] == 'scheduled' and post['channels'][0]['state'] == 'fb_scheduled'
    v = calls(mock, 'fb.videos')[-1]
    assert v['published'] == 'false' and abs(int(v['scheduled_publish_time']) - int(datetime.fromisoformat(when).timestamp())) < 2
    assert c.delete(f'/api/scheduled-posts/{post["id"]}', headers=h).json()['ok']
    assert calls(mock, 'fb.delete')[-1]['obj'] == post['channels'][0]['external_id']
    assert c.get('/api/scheduled-posts').json()['posts'][0]['status'] == 'cancelled'


def test_worker_tick_line_broadcast_retry_and_isolation(env, monkeypatch, tmp_path):
    monkeypatch.setenv('SCHEDULER_WORKER', '0')
    app, mock = env
    c, h, pid, proj, fb, ig = setup_user(app, mock, 'sched3')
    line = c.post('/api/connectors/line', headers=h, json={'channel_id': '1650000000', 'channel_secret': '0123456789abcdef0123456789abcdef',
                                                           'access_token': 'MOCK-LINE-LONG-TOKEN'}).json()['channel']
    when = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    body = {'product_id': pid, 'channel_ids': [line['id'], fb[1]['id']], 'caption': 'แฟลชเซล', 'scheduled_at': when}
    assert c.post('/api/scheduled-posts', headers=h, json=body).status_code == 400  # broadcast needs confirmation
    post = c.post('/api/scheduled-posts', headers=h, json={**body, 'confirm_broadcast': True}).json()['post']
    assert post['status'] == 'scheduled' and {x['state'] for x in post['channels']} == {'pending'}  # <15 min → our worker
    assert app.state.scheduler_tick() == []  # not due yet
    db = sqlite3.connect(tmp_path / 'community.db')
    db.execute('UPDATE scheduled_posts SET scheduled_at=? WHERE id=?', ((datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(timespec='seconds'), post['id']))
    db.commit()
    done = app.state.scheduler_tick()
    assert done == [{'id': post['id'], 'status': 'posted'}]
    assert calls(mock, 'line.broadcast') and calls(mock, 'fb.feed') or calls(mock, 'fb.photos')
    # failure + retry: disconnect a page before its time
    p2 = c.post('/api/scheduled-posts', headers=h, json={'product_id': pid, 'channel_ids': [fb[1]['id']], 'caption': 'x'}).json()['post']
    assert p2['status'] == 'posted'
    p3 = c.post('/api/scheduled-posts', headers=h, json={'product_id': pid, 'channel_ids': [fb[0]['id']], 'caption': 'y',
                                                         'scheduled_at': (datetime.now(timezone.utc) + timedelta(minutes=3)).isoformat()}).json()['post']
    c.delete(f'/api/connectors/{fb[0]["id"]}', headers=h)
    db.execute('UPDATE scheduled_posts SET scheduled_at=? WHERE id=?', ((datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(timespec='seconds'), p3['id'])); db.commit()
    app.state.scheduler_tick()
    st = next(x for x in c.get('/api/scheduled-posts').json()['posts'] if x['id'] == p3['id'])
    assert st['status'] == 'failed' and 'ตัดการเชื่อมต่อ' in st['channels'][0]['error']
    # past time rejected; another user cannot use my channels or see my posts
    assert c.post('/api/scheduled-posts', headers=h, json={'product_id': pid, 'channel_ids': [fb[1]['id']],
                                                         'scheduled_at': '2020-01-01T00:00:00Z'}).status_code == 400
    o = TestClient(app); ho = signup(o, 'intruder')
    assert o.post('/api/scheduled-posts', headers=ho, json={'product_id': pid, 'channel_ids': [fb[1]['id']]}).status_code == 404
    assert o.get('/api/scheduled-posts').json()['posts'] == []
    assert o.delete(f'/api/scheduled-posts/{post["id"]}', headers=ho).status_code == 404
