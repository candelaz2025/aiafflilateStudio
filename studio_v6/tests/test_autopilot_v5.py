"""No real API token or network needed. Verifies fail-closed offline autonomy."""
import importlib
import time

from fastapi.testclient import TestClient


def client_app(monkeypatch, tmp_path):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    for key in ('GEMINI_API_KEY','BRAVE_SEARCH_API_KEY','TIKTOK_CLIENT_KEY','TIKTOK_CLIENT_SECRET','TIKTOK_REDIRECT_URI','RADAR_TIKTOK_FEED_URL','RADAR_SHOPEE_FEED_URL'):
        monkeypatch.delenv(key, raising=False)
    import app
    importlib.reload(app)
    return app, TestClient(app.app)


def test_auto_discovery_prepares_only_confirmed_and_does_not_publish(monkeypatch,tmp_path):
    app,cli=client_app(monkeypatch,tmp_path)
    import autopilot
    monkeypatch.setattr(autopilot,'fetch_trends',lambda:[{'title':'ที่วางโทรศัพท์','source_name':'Google Trends Thailand (RSS)',
         'source_url':'https://trends.google.com/trending?geo=TH','category':'ของใช้','trend_traffic':1000}])
    body={'enabled':True,'auto_discover':True,'auto_prepare':True,'auto_generate':False,
          'max_new_drafts_per_cycle':3,'max_videos_per_day':2,'scan_hours':12,'allow_without_reference':False}
    assert cli.put('/api/autopilot/settings',json=body).status_code==200
    assert cli.post('/api/autopilot/tick').status_code==200
    for _ in range(100):
        x=cli.get('/api/autopilot/status').json()
        if any(a['kind']=='discovery' for a in x['logs']): break
        time.sleep(.03)
    assert any(a['kind']=='discovery' and a['state']=='ok' for a in x['logs'])
    listing=cli.get('/api/external').json()
    assert len(listing)==1
    assert cli.get('/api/drafts').json()==[], 'Google trends is NOT a confirmed affiliate item'
    assert cli.patch('/api/external/'+str(listing[0]['id'])+'/match',json={
        'tiktok_link':'https://shop.tiktok.com/example-product',
        'confirmed_tiktok':True,'shopee_link':'','confirmed_shopee':False,'features':'ที่วางมือถือ'}).status_code==200
    assert cli.post('/api/autopilot/tick').status_code==200
    for _ in range(100):
        queue=cli.get('/api/queue').json()
        if queue:break
        time.sleep(.03)
    assert len(queue)==1 and queue[0]['platform']=='tiktok'
    assert queue[0]['status']=='pending_review'
    assert cli.get('/api/tiktok/status').json()['connected'] is False
    assert cli.get('/api/autopilot/status').json()['providers']['google_veo'] is False
    # Browser tokens not necessary for a script, background posting is gated.
    assert cli.get('/api/tiktok/jobs').json()==[]


def test_paid_ai_cannot_be_enabled_without_key(monkeypatch,tmp_path):
    _,cli=client_app(monkeypatch,tmp_path)
    body={'enabled':True,'auto_generate':True,'max_videos_per_day':2}
    response=cli.put('/api/autopilot/settings',json=body)
    assert response.status_code==412
    assert cli.get('/api/autopilot/status').json()['config']['enabled'] is False


def test_tiktok_requires_approval_and_caption(monkeypatch,tmp_path):
    _,cli=client_app(monkeypatch,tmp_path)
    prod=cli.post('/api/products',json={'title':'เครื่องดูดฝุ่นรุ่น A'}).json()
    draft=cli.post('/api/drafts',json={'product_id':prod['id'],'platforms':['tiktok']}).json()['draft']
    queue=cli.get('/api/queue').json()[0]
    assert cli.post(f'/api/tiktok/queue/{queue["id"]}/approve',json={
        'privacy_level':'PUBLIC_TO_EVERYONE','scheduled_at':'2026-10-19T00:00:00+00:00',
        'caption':'#สินค้า','acknowledge_no_basket':True,'acknowledge_aigc_and_rights':True}).status_code==412
    assert cli.get('/api/tiktok/jobs').json()==[]
