"""Shopee Extra Comm discovery and per-account checks."""
from fastapi.testclient import TestClient
from community_app import create_app
from studio_v6 import product_discovery as pd
import sqlite3

KEY=b'HCMiHM3FNUmDDvPGmUKpkTMKyvIWUZSdLHvufz1qUdc='
PWD='StronglySecurePass123!'


def signup(c,n):
    r=c.post('/api/register',json={'username':f'ecuser{n}','email':f'ecuser{n}@test.dev','password':PWD})
    assert r.status_code==200,r.text
    return {'X-CSRF-Token':r.json()['csrf']}


def sample_fetch(endpoint,params,token=None):
    if 'bing' in endpoint:
        return ('''<rss><channel><item><title>EXTRA COMM แก้วน้ำ</title><link>https://shopee.co.th/product/121/11</link><description>Extra Comm อัตราใน Shopee Affiliate</description></item><item><title>สินค้าทั่วไป</title><link>https://shopee.co.th/product/33/44</link><description>สินค้าขายดี</description></item><item><title>หลอกโดเมน</title><link>https://other.test/shopee</link></item></channel></rss>''').encode()
    if 'news.google' in endpoint: return b'<rss><channel></channel></rss>'
    raise AssertionError(endpoint)


def test_hint_is_not_verified(monkeypatch):
    monkeypatch.setattr(pd,'fetch',sample_fetch);pd._cache.clear()
    r=pd.discover('แก้วน้ำ',extra_comm_only=True)
    assert len(r['items'])==1
    assert r['items'][0]['extra_comm_mentioned'] is True
    assert r['items'][0]['extra_comm_verified'] is False
    assert r['items'][0]['affiliate_verified'] is False
    assert r['items'][0]['commission'] is None
    assert len(pd.discover('แก้วน้ำ')['items'])==2
    assert pd.discover('แก้วน้ำ',extra_comm_only=True)['cached'] is True


def test_member_self_checked_privacy(tmp_path,monkeypatch):
    monkeypatch.setattr(pd,'fetch',sample_fetch);pd._cache.clear()
    app=create_app(tmp_path,secret_key=KEY)
    a=TestClient(app);b=TestClient(app);ah=signup(a,1);bh=signup(b,2)
    assert a.get('/api/my/radar/search?q=แก้วน้ำ&extra_comm_only=true').json()['extra_comm_mode'] is True
    product={'title':'Extra Comm Mug','url':'https://shopee.co.th/product/121/11',
             'platform':'shopee','extra_comm_checked':True,'extra_comm_rate':9}
    r=a.post('/api/my/products',json=product,headers=ah)
    assert r.status_code==200,r.text
    pid=r.json()['id']
    p=a.get('/api/my/products').json()[0]
    assert p['extra_comm_checked']==1 and p['extra_comm_rate']==9
    assert p['extra_comm_checked_at']
    assert b.get('/api/my/products').json()==[]
    assert b.patch(f'/api/my/products/{pid}/extra-comm',json={'checked':True,'rate':20},headers=bh).status_code==404
    assert a.patch(f'/api/my/products/{pid}/extra-comm',json={'checked':True,'rate':8.50},headers=ah).status_code==200
    assert a.get('/api/my/products').json()[0]['extra_comm_rate']==8.5
    assert a.patch(f'/api/my/products/{pid}/extra-comm',json={'checked':False,'rate':None},headers=ah).status_code==200
    assert a.get('/api/my/products').json()[0]['extra_comm_checked']==0
    assert a.get('/api/my/products').json()[0]['extra_comm_rate'] is None


def test_invalid_domains_rates_and_csrf(tmp_path):
    app=create_app(tmp_path,secret_key=KEY);c=TestClient(app);h=signup(c,5)
    cases=[('tiktok','https://shop.tiktok.com/view/product/3',10),
           ('shopee','https://shopee.co.th.evil.test/x',10),
           ('shopee','http://shopee.co.th/x',10),
           ('shopee','https://shopee.co.th/x',101),
           ('shopee','https://shopee.co.th/x',-1)]
    for platform,url,rate in cases:
        r=c.post('/api/my/products',json={'title':'Bad product','url':url,'platform':platform,
                  'extra_comm_checked':True,'extra_comm_rate':rate},headers=h)
        assert r.status_code in (400,422),r.text
    r=c.post('/api/my/products',json={'title':'Good Shopee','url':'https://s.shopee.co.th/abcd',
        'platform':'shopee','extra_comm_checked':True,'extra_comm_rate':5},headers=h)
    assert r.status_code==200,r.text
    pid=r.json()['id']
    assert c.patch(f'/api/my/products/{pid}/extra-comm',json={'checked':True,'rate':6}).status_code==403
    assert c.patch(f'/api/my/products/{pid}/extra-comm',json={'checked':True,'rate':6},headers=h).status_code==200


def test_second_init_preserves_products(tmp_path):
    app=create_app(tmp_path,secret_key=KEY);c=TestClient(app);h=signup(c,6)
    assert c.post('/api/my/products',json={'title':'Old saved item','url':'','platform':'other'},headers=h).status_code==200
    create_app(tmp_path,secret_key=KEY)
    with sqlite3.connect(tmp_path/'community.db') as db:
        assert db.execute('SELECT COUNT(*) FROM products').fetchone()[0]==1
        assert {'extra_comm_checked','extra_comm_rate','extra_comm_checked_at'} <= {r[1] for r in db.execute('PRAGMA table_info(products)')}
