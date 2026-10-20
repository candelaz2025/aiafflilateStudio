"""PC V6 fresh install and no-key behavior: no actual external credentials/network."""
import importlib
import os
import time
from pathlib import Path
from fastapi.testclient import TestClient


def test_first_start_lists_safely_labeled_ideas_when_offline(monkeypatch,tmp_path):
    monkeypatch.setenv('DATA_DIR',str(tmp_path))
    monkeypatch.setenv('EXTERNAL_AUTO_SCAN_MINUTES','0')
    import external_radar
    monkeypatch.setattr(external_radar,'fetch_trends',lambda:[])
    monkeypatch.setattr(external_radar,'fetch_product_news',lambda:[])
    import app
    importlib.reload(app)
    with TestClient(app.app) as c:
        status=c.get('/health')
        assert status.status_code==200
        candidates=c.get('/api/external').json()
        assert len(candidates)>=10
        assert all('ไม่ใช่ยอดขาย' in x['source_name'] for x in candidates)
        # Ideas cannot be treated as confirmed affiliate products.
        assert c.get('/api/drafts').json()==[]
        assert c.get('/api/queue').json()==[]
        r=c.post('/api/external/scan')
        assert r.status_code in (200,409)  # initial background scan may be in progress
        for _ in range(30):
            if c.get('/api/external/status').json()['latest']['source']!='starter_ideas':break
            time.sleep(.02)
        assert len(c.get('/api/external').json())>=10


def test_api_key_settings_do_not_echo_secret(monkeypatch,tmp_path):
    monkeypatch.setenv('DATA_DIR',str(tmp_path))
    import app
    importlib.reload(app)
    monkeypatch.setattr(app,'ROOT',tmp_path)
    with TestClient(app.app) as c:
        resp=c.post('/api/setup/keys',json={'gemini_api_key':'v6_fake_secret_for_test'})
        assert resp.status_code==200
        assert 'v6_fake_secret_for_test' not in resp.text
        status=c.get('/api/setup')
        assert status.status_code==200 and status.json()['gemini_api_key'] is True
        assert 'v6_fake_secret_for_test' not in status.text
        assert 'v6_fake_secret_for_test' in (tmp_path/'.env').read_text()
    monkeypatch.delenv('GEMINI_API_KEY',raising=False)
