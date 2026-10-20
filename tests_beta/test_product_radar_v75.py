import pytest
from fastapi.testclient import TestClient
from community_app import create_app
from studio_v6 import product_discovery as pd

KEY=b'HCMiHM3FNUmDDvPGmUKpkTMKyvIWUZSdLHvufz1qUdc='
PASSWORD='ExcellentPass123456'


def signup(client, num):
    response=client.post('/api/register',json={
        'username':f'finder{num}','email':f'finder{num}@example.com','password':PASSWORD})
    assert response.status_code==200,response.text
    return {'X-CSRF-Token':response.json()['csrf']}


def fake_fetch(endpoint,params,token=None):
    if endpoint.endswith('/web/search'):
        assert token=='BRAVE_TEST_12345678'
        return b'{"web":{"results":[{"title":"Gadget from TikTok shop","url":"https://shop.tiktok.com/view/product/456","description":"candidate"}]}}'
    if 'bing.com' in endpoint:
        return '''<rss><channel><item><title>Shopee Coffee Mug</title><link>https://shopee.co.th/product/111/222</link><description>Web index result</description></item><item><title>Not a product</title><link>https://example.org/item</link></item></channel></rss>'''.encode()
    if 'news.google.com' in endpoint:
        return '''<rss><channel><item><title>Coffee Mug Review</title><link>https://example.org/review</link><description>Review only</description></item></channel></rss>'''.encode()
    raise AssertionError(endpoint)


def test_discovery_sources_and_evidence(monkeypatch):
    monkeypatch.setattr(pd,'fetch',fake_fetch)
    pd._cache.clear()
    result=pd.discover('แก้วกาแฟ',token='BRAVE_TEST_12345678')
    assert result['listing_candidates']==2
    assert len(result['items'])==3
    assert all(i['sales_verified'] is False and i['affiliate_verified'] is False for i in result['items'])
    assert result['items'][-1]['kind']=='article_lead'
    assert result['search_links']['shopee'].startswith('https://shopee.co.th/search?')
    assert result['has_brave_key'] is True
    assert 'BRAVE_TEST' not in str(result)
    assert pd.discover('แก้วกาแฟ',token='BRAVE_TEST_12345678')['cached'] is True


def test_member_integration_save_to_script_and_isolation(tmp_path,monkeypatch):
    monkeypatch.setattr(pd,'fetch',fake_fetch)
    pd._cache.clear()
    app=create_app(tmp_path,secret_key=KEY)
    a=TestClient(app); b=TestClient(app)
    ha=signup(a,1); hb=signup(b,2)
    assert a.get('/api/my/radar/search?q=x').status_code==400
    assert a.get('/api/my/radar/search?q=%E0%B9%81%E0%B8%81%E0%B9%89%E0%B8%A7%E0%B8%81%E0%B8%B2%E0%B9%81%E0%B8%9F').status_code==200
    assert a.put('/api/my/keys/brave',json={'key':'BRAVE_TEST_12345678'},headers=ha).status_code==200
    r=a.get('/api/my/radar/search?q=%E0%B9%81%E0%B8%81%E0%B9%89%E0%B8%A7%E0%B8%81%E0%B8%B2%E0%B9%81%E0%B8%9F')
    assert r.status_code==200,r.text
    body=r.json(); assert body['listing_candidates']==2
    assert 'BRAVE_TEST' not in r.text
    assert b.get('/api/my/keys').json()['connected']==[]
    other=b.get('/api/my/radar/search?q=%E0%B9%81%E0%B8%81%E0%B9%89%E0%B8%A7%E0%B8%81%E0%B8%B2%E0%B9%81%E0%B8%9F').json()
    assert other['has_brave_key'] is False
    assert other['listing_candidates']==1
    product=body['items'][0]
    created=a.post('/api/my/products',headers=ha,json={
       'title':product['title'],'platform':product['platform'],'url':product['url']})
    assert created.status_code==200,created.text
    pid=created.json()['id']
    assert b.get('/api/my/products').json()==[]
    drafted=a.post('/api/my/drafts',headers=ha,json={'product_id':pid,'style':'pov'})
    assert drafted.status_code==200,drafted.text
    assert drafted.json()['status']=='draft_only'
    assert b.post('/api/my/drafts',headers=hb,json={'product_id':pid,'style':'pov'}).status_code==404
    assert b.get('/api/my/radar/search?q=test').status_code==200
    assert TestClient(app).get('/api/my/radar/search?q=hello').status_code==401


def test_no_results_never_substitute_fake_sales(monkeypatch):
    pd._cache.clear()
    def failed(*args,**kwargs):raise ValueError('network unavailable')
    monkeypatch.setattr(pd,'fetch',failed)
    result=pd.discover('สายชาร์จUSB-C')
    assert result['items']==[]
    assert len(result['sources'])==2
    assert all(x['status']=='unavailable' for x in result['sources'])
    assert 'ยอดขาย' in result['note']


def test_link_rules_and_safety():
    assert pd.clean_url('http://shopee.co.th/test')==''
    assert pd.clean_url('https://bad:pass@shopee.co.th/test')==''
    assert pd.clean_url('https://localhost/test')==''
    assert pd.platform_of('https://badshopee.co.th/item')=='other'
    assert pd.platform_of('https://shopee.co.th/item')=='shopee'
    assert pd.platform_of('https://shop.tiktok.com/view/product/5')=='tiktok'


def test_auto_topics_live_labels(monkeypatch):
    pd._cache.clear()
    def stub(endpoint,params,token=None):
        if 'trends.google.com' in endpoint:
            return '<rss><channel><item><title>พัดลมพกพา</title><link>https://trends.google.com/trending?geo=TH</link></item><item><title>ผลบอลวันนี้</title><link>https://trends.google.com/trending</link></item></channel></rss>'.encode()
        return '<rss><channel><item><title>รีวิวหูฟังไร้สายรุ่นใหม่</title><link>https://news.google.com/articles/test</link></item></channel></rss>'.encode()
    monkeypatch.setattr(pd,'fetch',stub)
    resp=pd.trending_topics()
    assert len(resp['topics'])==2
    assert resp['topics'][0]['keyword']=='พัดลมพกพา'
    assert all(t['sales_verified'] is False for t in resp['topics'])
    app=create_app(__import__('tempfile').mkdtemp(),secret_key=KEY)
    c=TestClient(app);signup(c,89)
    r=c.get('/api/my/radar/trending')
    assert r.status_code==200 and len(r.json()['topics'])==2
