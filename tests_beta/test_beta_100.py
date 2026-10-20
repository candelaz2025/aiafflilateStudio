import os
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from community_app import create_app

KEY=b'HCMiHM3FNUmDDvPGmUKpkTMKyvIWUZSdLHvufz1qUdc='
PASS='ExcellentPass123456'


def register(c,n,invite=''):
    return c.post('/api/register',json={'username':f'beta{n:04d}','email':f'beta{n:04d}@example.org','password':PASS,'invite_code':invite})


def test_100_member_limit_atomic(tmp_path,monkeypatch):
    monkeypatch.setattr('community_app.MAX_BETA_USERS', 100)
    app=create_app(tmp_path,secret_key=KEY)
    # Tests actual 100 registrations through HTTP requests; not just mock SQL counts.
    with TestClient(app) as c:
        for n in range(100):
            assert register(c,n).status_code==200,n
        assert c.get('/api/beta/capacity').json()=={'limit':100,'registered':100,'remaining':0,'invite_only':False}
        fail=register(c,100)
        assert fail.status_code==409, fail.text
        assert c.get('/api/me').status_code==200


def test_private_drafts_queue_and_key_isolation(tmp_path,monkeypatch):
    monkeypatch.setattr('community_app.MAX_BETA_USERS',100)
    app=create_app(tmp_path,secret_key=KEY)
    alice=TestClient(app);bob=TestClient(app)
    ac=register(alice,1).json()['csrf']; bc=register(bob,2).json()['csrf']
    h_a={'X-CSRF-Token':ac}; h_b={'X-CSRF-Token':bc}
    created=alice.post('/api/my/products',json={'title':'My air fryer','platform':'shopee'},headers=h_a)
    assert created.status_code==200
    pid=created.json()['id']
    assert bob.get('/api/my/products').json()==[]
    assert bob.post('/api/my/drafts',json={'product_id':pid,'style':'pov'},headers=h_b).status_code==404
    d=alice.post('/api/my/drafts',json={'product_id':pid,'style':'pov'},headers=h_a)
    assert d.status_code==200,d.text
    did=d.json()['id']
    assert 'ยังไม่ได้สร้างไฟล์วิดีโอ' in d.json()['notice']
    assert bob.get('/api/my/drafts').json()==[]
    assert bob.post('/api/my/queue',json={'draft_id':did,'platform':'tiktok'},headers=h_b).status_code==404
    q=alice.post('/api/my/queue',json={'draft_id':did,'platform':'tiktok'},headers=h_a)
    assert q.status_code==200,q.text
    qid=q.json()['id']
    assert q.json()['status']=='needs_review'
    assert bob.get('/api/my/queue').json()==[]
    assert bob.patch(f'/api/my/queue/{qid}',json={'status':'cancelled'},headers=h_b).status_code==404
    assert alice.patch(f'/api/my/queue/{qid}',json={'status':'completed_manual'}).status_code==403
    assert alice.patch(f'/api/my/queue/{qid}',json={'status':'completed_manual'},headers=h_a).status_code==200
    assert bob.put('/api/my/keys/gemini',json={'key':'bob-private-key-001'},headers=h_b).status_code==200
    assert alice.get('/api/my/keys').json()['connected']==[]
    assert 'bob-private-key' not in str(bob.get('/api/my/keys').json())
    assert alice.get('/studio/').status_code==403


def test_concurrent_last_places(tmp_path,monkeypatch):
    monkeypatch.setattr('community_app.MAX_BETA_USERS',5)
    app=create_app(tmp_path,secret_key=KEY)
    def run(n):
        with TestClient(app) as c:
            return register(c,n).status_code
    with ThreadPoolExecutor(max_workers=10) as pool:
        codes=list(pool.map(run,range(15)))
    assert codes.count(200)==5,codes
    assert codes.count(409)==10,codes
    with TestClient(app) as c:
        assert c.get('/api/beta/capacity').json()['registered']==5


def test_login_throttle_and_security_headers(tmp_path):
    app=create_app(tmp_path,secret_key=KEY)
    with TestClient(app) as c:
        register(c,1)
        for _ in range(8):
            assert c.post('/api/login',json={'email':'beta0001@example.org','password':'WrongPass123456'}).status_code==401
        assert c.post('/api/login',json={'email':'beta0001@example.org','password':PASS}).status_code==429
        resp=c.get('/')
        assert resp.status_code==200
        assert resp.headers['x-content-type-options']=='nosniff'
        assert resp.headers['x-frame-options']=='DENY'
        assert 'Product Radar' in resp.text
