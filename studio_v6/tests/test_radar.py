import importlib
import io

from fastapi.testclient import TestClient


def new_client(monkeypatch,tmp_path):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    for k in ('RADAR_TIKTOK_FEED_URL','RADAR_SHOPEE_FEED_URL','RADAR_ALLOWED_FEED_HOSTS','RADAR_AUTO_SYNC_MINUTES','OPENAI_API_KEY'):
        monkeypatch.delenv(k,raising=False)
    import app
    importlib.reload(app)
    return app, TestClient(app.app)


def test_radar_csv_ranks_filters_promotes_and_is_idempotent(monkeypatch,tmp_path):
    module,client=new_client(monkeypatch,tmp_path)
    assert client.get('/api/radar/status').json()['count']==0
    assert client.post('/api/radar/sync').status_code==412
    csv_text=('title,price,commission_pct,units_sold_30d,rating,reviews,url,features,external_id\n'
              'แก้วพกพา,259,12,5000,4.8,2100,https://example.com/p1,มีฝาปิด,a123\n'
              'ขาตั้งมือถือ,170,19,900,4.4,80,https://example.com/p2,พับได้,b234\n'
              'หมวกกันแดด,100,, ,4.2,,https://example.com/p3,มีปีกหมวก,c345\n')
    res=client.post('/api/radar/import?platform=shopee',files={'file':('x.csv',csv_text.encode('utf-8'),'text/csv')})
    assert res.status_code==200,res.text
    assert res.json()['count']==3
    got=client.get('/api/radar').json()
    assert len(got)==3
    assert got[0]['units_sold'] is not None
    assert got[-1]['sales_period']=='missing'
    assert client.get('/api/radar?min_sales=1000').json()[0]['title']=='แก้วพกพา'
    good=client.post('/api/radar/prepare-top',json={'platform':'shopee','limit':3,'min_sales':100,'min_commission':5})
    assert good.status_code==200, good.text
    assert good.json()['prepared']==2
    assert len(client.get('/api/products').json())==2
    assert len(client.get('/api/drafts').json())==2
    assert len(client.get('/api/queue').json())==2
    assert {r['platform'] for r in client.get('/api/queue').json()} == {'shopee'}
    assert client.post('/api/radar/prepare-top',json={'platform':'all'}).json()['prepared']==0
    again=client.post(f'/api/radar/{got[0]["id"]}/prepare')
    assert again.status_code==200
    assert again.json()['created'] is False
    assert len(client.get('/api/products').json())==2
    assert client.get('/api/status').json()['counts']['radar']==3
    # Reimport updates numbers without duplicates and retains prepared draft references.
    csv2='title,units_sold_30d,external_id\nแก้วพกพา,7000,a123\n'
    client.post('/api/radar/import?platform=shopee',files={'file':('again.csv',csv2.encode(),'text/csv')})
    assert len(client.get('/api/radar').json())==3
    row=next(r for r in client.get('/api/radar').json() if r['external_id']=='a123')
    assert row['units_sold']==7000 and row['draft_id'] is not None


def test_authorized_feed_sync_and_permissions(monkeypatch,tmp_path):
    module,client=new_client(monkeypatch,tmp_path)
    monkeypatch.setenv('RADAR_TIKTOK_FEED_URL','https://approved.example/api/products')
    assert client.post('/api/radar/sync').json()['sources']['tiktok']['state']=='error'
    assert client.get('/api/radar').json()==[]
    monkeypatch.setenv('RADAR_ALLOWED_FEED_HOSTS','approved.example')
    class FakeResponse:
        status_code=200
        def raise_for_status(self):pass
        def iter_content(self,chunk_size):
            yield b'{"products":[{"title":"Portable stand","units_sold":700,"commission_pct":14,"external_id":"abc"}]}'
        def close(self):pass
    def fake_request(url,**kwargs):
        assert kwargs['allow_redirects'] is False
        return FakeResponse()
    monkeypatch.setattr('radar.requests.get',fake_request)
    result=client.post('/api/radar/sync').json()
    assert result['count']==1
    assert result['sources']['shopee']['state']=='not_connected'
    assert client.get('/api/radar?platform=tiktok').json()[0]['title']=='Portable stand'
    assert client.get('/api/radar?platform=shopee').json()==[]


def test_invalid_csv_and_bad_scores(monkeypatch,tmp_path):
    module,client=new_client(monkeypatch,tmp_path)
    assert client.post('/api/radar/import?platform=wrong', files={'file':('x.csv',b'hi','text/csv')}).status_code==400
    assert client.post('/api/radar/import?platform=tiktok', files={'file':('x.txt',b'hi','text/plain')}).status_code==400
    csv_text='title,price,commission_pct,units_sold,rating,url\nStrange sale,-90,999,nan,9,javascript:alert(1)\n'
    result=client.post('/api/radar/import?platform=tiktok',files={'file':('x.csv',csv_text.encode(),'text/csv')})
    assert result.json()['count']==1
    row=client.get('/api/radar').json()[0]
    assert row['price'] is None and row['rating'] is None and row['commission_pct'] is None
    assert row['units_sold'] is None and row['url']==''
