import sqlite3
from fastapi.testclient import TestClient
from community_app import create_app

SECRET=b'HCMiHM3FNUmDDvPGmUKpkTMKyvIWUZSdLHvufz1qUdc='

def sign(client,username):
    r=client.post('/api/register',json={'username':username,'email':f'{username}@example.com','password':'SecretPass12345'})
    assert r.status_code==200,r.text
    return r.json()['csrf']

def test_all_pieces_work_together(tmp_path):
    app=create_app(tmp_path, secret_key=SECRET)
    user=TestClient(app); admin=TestClient(app); anon=TestClient(app)
    assert anon.get('/').status_code==200
    assert anon.get('/donate').status_code==200
    assert anon.get('/updates').status_code==200
    assert anon.get('/studio/api/products').status_code==401
    assert anon.get('/studio/static/app.js').status_code==401
    assert anon.get('/studio/',follow_redirects=False).status_code==303
    assert anon.post('/studio/api/products',json={'title':'x'}).status_code==401
    cu=sign(user,'member_u');ca=sign(admin,'owner_a')
    assert user.get('/studio/').status_code==403
    assert user.get('/studio/api/products').status_code==403
    assert user.get('/studio/static/app.js').status_code==403
    assert user.post('/studio/api/products',json={'title':'member attempt'},headers={'X-CSRF-Token':cu}).status_code==403
    # Admin's role is reassessed against DB on every request.
    with sqlite3.connect(tmp_path/'community.db') as db:
        db.execute("UPDATE users SET role='admin' WHERE username='owner_a'")
    assert admin.get('/studio/').status_code==200
    s=admin.get('/studio/').text
    assert '/studio/static/app.js' in s and 'ค้นหาจากเว็บภายนอก' in s
    js=admin.get('/studio/static/app.js').text
    assert "'/studio/api/" in js and "'X-CSRF-Token'" in js
    assert admin.get('/studio/api/status').status_code==200
    assert admin.get('/studio/api/external/status').status_code==200
    assert admin.get('/studio/api/radar/status').status_code==200
    assert admin.get('/studio/api/setup').status_code==200
    assert admin.post('/studio/api/products',json={'title':'Admin product'}).status_code==403
    created=admin.post('/studio/api/products',json={'title':'Admin product','features':'ขนาดมาตรฐาน'},headers={'X-CSRF-Token':ca})
    assert created.status_code==200,created.text
    pid=created.json()['id']
    drafted=admin.post('/studio/api/drafts',json={'product_id':pid,'platforms':['tiktok','shopee']},headers={'X-CSRF-Token':ca})
    assert drafted.status_code==200,drafted.text
    drafts=admin.get('/studio/api/drafts').json()
    assert any(x['product_id']==pid for x in drafts)
    q=admin.get('/studio/api/queue').json()
    assert any(x['draft_id']==drafted.json()['draft']['id'] for x in q)
    assert len(user.get('/api/my/products').json())==0
    memberproduct=user.post('/api/my/products',json={'title':'User private thing','platform':'shopee'},headers={'X-CSRF-Token':cu})
    assert memberproduct.status_code==200
    assert admin.get('/api/my/products').json()==[]
    assert admin.get('/studio/api/products').json()[-1]['title']=='Admin product'
    assert user.get('/api/my/products').json()[0]['title']=='User private thing'
    assert user.get('/api/my/keys').json()['connected']==[]
    assert admin.get('/health').json()['ok']
    assert admin.get('/api/system/version').json()['version']=='0.7.10'


def test_csrf_and_static_asset_protected(tmp_path):
    app=create_app(tmp_path,secret_key=SECRET)
    c=TestClient(app)
    csrf=sign(c,'ownerxx')
    with sqlite3.connect(tmp_path/'community.db') as db:
        db.execute("UPDATE users SET role='admin' WHERE username='ownerxx'")
    assert c.put('/studio/api/autopilot/settings',json={'enabled':False}).status_code==403
    assert c.post('/studio/api/products',json={'title':'okay okay'},headers={'X-CSRF-Token':'notcsrf'}).status_code==403
    assert c.post('/studio/api/products',json={'title':'okay okay'},headers={'X-CSRF-Token':csrf}).status_code==200
    assert c.get('/studio/api/products').status_code==200

