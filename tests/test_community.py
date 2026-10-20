from pathlib import Path
import sqlite3
import pytest
from fastapi.testclient import TestClient
from community_app import create_app

@pytest.fixture
def clients(tmp_path):
    app = create_app(tmp_path, secret_key=b'HCMiHM3FNUmDDvPGmUKpkTMKyvIWUZSdLHvufz1qUdc=')
    return TestClient(app), TestClient(app), tmp_path

def signup(c,username,email):
    r=c.post('/api/register',json={'username':username,'email':email,'password':'SecretPass12345'})
    assert r.status_code==200, r.text
    return r.json()['csrf']

def auth(csrf):
    return {'X-CSRF-Token':csrf}

def test_public_access_and_health(clients):
    a,_,_=clients
    assert a.get('/health').json()['ok']
    assert a.get('/').status_code==200
    assert a.get('/api/ideas').status_code==401
    assert a.get('/api/products').status_code==404   # Don't expose old V6 unauthenticated routes.

def test_register_login_logout_and_csrf(clients):
    a,b,_=clients
    token=signup(a,'alice','alice@example.com')
    assert a.get('/api/me').json()['username']=='alice'
    assert a.post('/api/ideas',json={'kind':'feature','title':'Search products faster','body':'Please optimize the search speed'}).status_code==403
    assert a.post('/api/logout',headers=auth(token)).status_code==200
    assert a.get('/api/me').status_code==401
    assert a.post('/api/login',json={'email':'alice@example.com','password':'wrongPass123456'}).status_code==401
    assert a.post('/api/login',json={'email':'alice@example.com','password':'SecretPass12345'}).status_code==200
    assert b.get('/api/me').status_code==401

def test_shared_ideas_votes_comments_admin_only(clients):
    a,b,folder=clients
    ca=signup(a,'alice','alice@example.com');cb=signup(b,'bob','bob@example.com')
    idea=a.post('/api/ideas',json={'kind':'feature','title':'ระบบหาไอเดียสินค้า','body':'ขอให้มีการตรวจสอบหลายแหล่งข้อมูล'},headers=auth(ca))
    assert idea.status_code==200, idea.text
    iid=idea.json()['id']
    assert len(b.get('/api/ideas').json())==1
    assert b.post(f'/api/ideas/{iid}/vote',headers=auth(cb)).json()['voted'] is True
    assert a.get('/api/ideas').json()[0]['votes']==1
    assert b.post(f'/api/ideas/{iid}/vote',headers=auth(cb)).json()['voted'] is False
    assert a.get('/api/ideas').json()[0]['votes']==0
    c=b.post(f'/api/ideas/{iid}/comments',json={'body':'เห็นด้วยครับ'},headers=auth(cb))
    assert c.status_code==200
    assert a.get(f'/api/ideas/{iid}/comments').json()[0]['author']=='bob'
    assert b.patch(f'/api/ideas/{iid}/status',json={'status':'released'},headers=auth(cb)).status_code==403
    with sqlite3.connect(folder/'community.db') as db:
        db.execute("UPDATE users SET role='admin' WHERE username='alice'")
    assert a.patch(f'/api/ideas/{iid}/status',json={'status':'planned'},headers=auth(ca)).json()['status']=='planned'
    assert b.get('/api/ideas').json()[0]['status']=='planned'

def test_byok_encryption_and_user_isolation(clients):
    a,b,folder=clients
    ca=signup(a,'alice','alice@example.com');cb=signup(b,'bob','bob@example.com')
    secret='sk-ALICE-ONLY-SECRET-1234567890'
    r=a.put('/api/my/keys/gemini',json={'key':secret},headers=auth(ca))
    assert r.status_code==200,r.text
    assert [x['provider'] for x in a.get('/api/my/keys').json()['connected']]==['gemini']
    assert b.get('/api/my/keys').json()['connected']==[]
    with sqlite3.connect(folder/'community.db') as db:
        row=db.execute('SELECT encrypted FROM credentials').fetchone()[0]
    assert secret not in row
    assert secret not in (folder/'community.db').read_bytes().decode('latin-1')
    assert b.delete('/api/my/keys/gemini',headers=auth(cb)).status_code==200
    assert len(a.get('/api/my/keys').json()['connected'])==1
    assert a.delete('/api/my/keys/gemini',headers=auth(ca)).status_code==200
    assert a.get('/api/my/keys').json()['connected']==[]
    assert a.put('/api/my/keys/tiktok',json={'key':'not-a-password-123'},headers=auth(ca)).status_code==400

def test_user_products_are_private(clients):
    a,b,_=clients
    ca=signup(a,'alice','alice@example.com');cb=signup(b,'bob','bob@example.com')
    r=a.post('/api/my/products',headers=auth(ca),json={'title':'Alice private product','platform':'shopee','url':'https://shopee.co.th/example'})
    assert r.status_code==200,r.text
    assert a.get('/api/my/products').json()[0]['title']=='Alice private product'
    assert b.get('/api/my/products').json()==[]
    assert b.post('/api/my/products',headers=auth(cb),json={'title':'bad link','platform':'tiktok','url':'javascript:evil()'}).status_code==400

def test_duplicate_registration_and_bad_role(clients):
    a,b,_=clients
    signup(a,'alice','alice@example.com')
    assert b.post('/api/register',json={'username':'ALICE','email':'other@example.com','password':'SecretPass12345'}).status_code==409
    assert b.post('/api/register',json={'username':'bob','email':'alice@example.com','password':'SecretPass12345'}).status_code==409
    assert b.post('/api/register',json={'username':'bob','email':'bob@example.com','password':'weakpass'}).status_code==422

def test_no_credentials_in_public_status(clients):
    a,_,_=clients
    ca=signup(a,'alice','alice@example.com')
    a.put('/api/my/keys/brave',json={'key':'brave-EXAMPLE-API-KEY-123'},headers=auth(ca))
    assert 'brave-EXAMPLE-API-KEY' not in a.get('/api/my/keys').text
    assert 'brave-EXAMPLE-API-KEY' not in a.get('/health').text
