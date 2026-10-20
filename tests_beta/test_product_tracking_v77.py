"""V7.7 Product reuse and user-reported sales metrics. No live commerce API data."""
import sqlite3
from fastapi.testclient import TestClient
from community_app import create_app

KEY=b'HCMiHM3FNUmDDvPGmUKpkTMKyvIWUZSdLHvufz1qUdc='
PWD='StronglySecurePass123!'


def signup(c, who):
    r=c.post('/api/register',json={'username':f'track{who}','email':f'track{who}@test.dev','password':PWD})
    assert r.status_code==200,r.text
    return {'X-CSRF-Token':r.json()['csrf']}


def product(c,h,title='Shopee Gift'):
    r=c.post('/api/my/products',json={'title':title,'platform':'shopee','url':'https://shopee.co.th/product/999/123'},headers=h)
    assert r.status_code==200,r.text
    return r.json()['id']


def draft(c,h,pid):
    return c.post('/api/my/drafts',json={'product_id':pid,'style':'pov'},headers=h)


def performance(views=100,clicks=20,orders=5,sales='700.50',commission='70.05'):
    return {'views':views,'clicks':clicks,'orders':orders,'sales_baht':sales,'commission_baht':commission,'note':'ยอดหลังโพสต์ 7 วัน'}


def test_reuse_tracking_and_manual_metrics(tmp_path):
    app=create_app(tmp_path,secret_key=KEY); c=TestClient(app); h=signup(c,1);pid=product(c,h)
    a=draft(c,h,pid);b=draft(c,h,pid)
    assert a.status_code==200 and b.status_code==200
    assert a.json()['use_number']==1 and b.json()['use_number']==2
    overview=c.get('/api/my/product-tracking').json();summary=overview['products'][0]
    assert summary['use_count']==2 and summary['reported_count']==0 and summary['last_used_at']
    assert summary['performance_label']=='ยังไม่บันทึกผล'
    hist=c.get(f'/api/my/products/{pid}/history').json()['events']
    assert len(hist)==2 and hist[0]['use_number']==2
    assert hist[0]['created_at'] and hist[0]['draft_id']==b.json()['id']
    url=f"/api/my/drafts/{a.json()['id']}/performance"
    r=c.put(url,json=performance(),headers=h)
    assert r.status_code==200,r.text
    assert r.json()['source']=='member_reported'
    x=c.get('/api/my/product-tracking').json()['products'][0]
    assert x['views']==100 and x['clicks']==20 and x['orders']==5
    assert x['sales_satang']==70050 and x['commission_satang']==7005
    assert '≥ 5' in x['performance_label']
    # PUT overwrites the cumulative stats for this draft; does not double revenue/orders.
    assert c.put(url,json=performance(200,30,7,'900.00','90.00'),headers=h).status_code==200
    x=c.get('/api/my/product-tracking').json()['products'][0]
    assert x['orders']==7 and x['commission_satang']==9000
    assert c.put(f"/api/my/drafts/{b.json()['id']}/performance",json=performance(300,50,2,'300','50'),headers=h).status_code==200
    x=c.get('/api/my/product-tracking').json()['products'][0]
    assert x['views']==500 and x['orders']==9 and x['commission_satang']==14000
    assert c.get(f'/api/my/products/{pid}/history').json()['events'][0]['orders']==2


def test_isolated_private_metrics_and_csrf(tmp_path):
    app=create_app(tmp_path,secret_key=KEY)
    a=TestClient(app);b=TestClient(app);ah=signup(a,2);bh=signup(b,3)
    aid=product(a,ah,'Secret item');did=draft(a,ah,aid).json()['id']
    assert b.get('/api/my/product-tracking').json()['products']==[]
    assert b.get(f'/api/my/products/{aid}/history').status_code==404
    assert b.put(f'/api/my/drafts/{did}/performance',json=performance(),headers=bh).status_code==404
    assert a.put(f'/api/my/drafts/{did}/performance',json=performance()).status_code==403
    assert a.get('/api/my/product-tracking').json()['products'][0]['orders']==0
    assert a.get('/api/my/product-tracking').status_code==200
    assert TestClient(app).get('/api/my/product-tracking').status_code==401


def test_invalid_metrics_do_not_change_previous_value(tmp_path):
    app=create_app(tmp_path,secret_key=KEY); c=TestClient(app); h=signup(c,4);pid=product(c,h);did=draft(c,h,pid).json()['id']
    path=f'/api/my/drafts/{did}/performance'
    assert c.put(path,json=performance(100,10,1,'50.00','5.00'),headers=h).status_code==200
    cases=[performance(-1,0,0),performance(1,-1,0),performance(10,30,1),
           performance(5,0,0,'-1','0'),performance(5,0,0,'12.123','0'),
           performance(5,0,0,'0','1000000001')]
    for body in cases:
        r=c.put(path,json=body,headers=h)
        assert r.status_code in (400,422),r.text
    x=c.get('/api/my/product-tracking').json()['products'][0]
    assert x['views']==100 and x['orders']==1 and x['commission_satang']==500


def test_upgrade_from_v76_backfills_old_drafts(tmp_path):
    app=create_app(tmp_path,secret_key=KEY);c=TestClient(app);h=signup(c,5)
    pid=product(c,h)
    r=draft(c,h,pid);did=r.json()['id']
    with sqlite3.connect(tmp_path/'community.db') as db:
        db.execute('DELETE FROM product_use_events')
        assert db.execute('SELECT COUNT(*) FROM drafts').fetchone()[0]==1
    create_app(tmp_path,secret_key=KEY)
    one=c.get(f'/api/my/products/{pid}/history').json()['events']
    assert len(one)==1 and one[0]['draft_id']==did and one[0]['use_number']==1
    create_app(tmp_path,secret_key=KEY)
    assert len(c.get(f'/api/my/products/{pid}/history').json()['events'])==1
    assert draft(c,h,pid).json()['use_number']==2


def test_reuse_concurrency_no_duplicate_use_numbers(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    app=create_app(tmp_path,secret_key=KEY);c=TestClient(app);h=signup(c,6);pid=product(c,h)
    def work(i):
        client=TestClient(app)
        for cookie in c.cookies.jar: client.cookies.set(cookie.name,cookie.value)
        response=client.post('/api/my/drafts',headers=h,json={'product_id':pid,'style':'pov'})
        return response
    with ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(work,range(6)))
    assert all(x.status_code==200 for x in results),[(x.status_code,x.text) for x in results]
    assert sorted(x.json()['use_number'] for x in results)==list(range(1,7))
    assert c.get('/api/my/product-tracking').json()['products'][0]['use_count']==6
