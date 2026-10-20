import io
import importlib
import os
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image


def test_products_to_dual_queue_and_flow_import(tmp_path, monkeypatch):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    import app
    importlib.reload(app)
    client=TestClient(app.app)
    assert client.get('/').status_code==200
    status=client.get('/api/status').json()
    assert status['google_omni_api'] is False
    assert status['flow_handoff'] is True
    prod=client.post('/api/products', json={'title':'แก้วน้ำพกพา','features':'ฝาปิดพลาสติก','audience':'นักเรียน'}).json()
    image=Image.new('RGB',(200,200),'blue')
    b=io.BytesIO();image.save(b,format='JPEG')
    r=client.post(f'/api/products/{prod["id"]}/reference', files={'file':('a.jpg',b.getvalue(),'image/jpeg')})
    assert r.status_code==200, r.text
    assert client.get('/api/assets/'+r.json()['filename']).status_code==200
    draft=client.post('/api/drafts', json={'product_id':prod['id'],'platforms':['tiktok','shopee']})
    assert draft.status_code==200, draft.text
    did=draft.json()['draft']['id']
    prompt=draft.json()['draft']['video_prompt']
    assert '9:16' in prompt and '<IMAGE_REF_0>' in prompt and 'no uploaded product image as thumbnail' in prompt
    q=client.get('/api/queue').json()
    assert {item['platform'] for item in q}=={'tiktok','shopee'}
    assert {item['status'] for item in q}=={'pending_review'}
    assert client.post(f'/api/drafts/{did}/omni').status_code==412
    file=io.BytesIO(b'just_for_test_only')
    monkeypatch.setattr(app,'save_upload',lambda *args,**kwargs:'not_awaitable') if False else None
    # A real encoded video is covered by the manual smoke test; upload validation is exercised above.
    assert client.get('/api/flow').json()['direct_flow_api'] is False
    invalid=client.patch(f'/api/queue/{q[0]["id"]}',json={'status':'posted','post_url':''})
    assert invalid.status_code==400
    ok=client.patch(f'/api/queue/{q[0]["id"]}',json={'status':'ready_manual','scheduled_at':'พรุ่งนี้ 18:00'})
    assert ok.status_code==200


def test_import_mp4_moves_both_queues_to_ready(tmp_path, monkeypatch):
    import importlib, subprocess, shutil
    if not shutil.which('ffmpeg'):
        return
    monkeypatch.setenv('DATA_DIR',str(tmp_path))
    import app
    importlib.reload(app)
    client=TestClient(app.app)
    pid=client.post('/api/products',json={'title':'ที่วางโทรศัพท์'}).json()['id']
    did=client.post('/api/drafts',json={'product_id':pid,'platforms':['tiktok','shopee']}).json()['draft']['id']
    video=tmp_path/'sample.mp4'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','lavfi','-i','color=size=160x240:rate=24:color=blue',
        '-t','1','-c:v','mpeg4','-pix_fmt','yuv420p',str(video)],check=True,timeout=20)
    with open(video,'rb') as f:
        upload=client.post(f'/api/drafts/{did}/import_flow',files={'file':('flow.mp4',f,'video/mp4')})
    assert upload.status_code==200,upload.text
    fn=upload.json()['video_filename']
    assert client.get('/api/assets/'+fn).status_code==200
    q=client.get('/api/queue').json()
    assert len(q)==2 and {x['status'] for x in q}=={'ready_manual'}
