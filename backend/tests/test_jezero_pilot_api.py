import json

from fastapi.testclient import TestClient

from app.main import app


def test_jezero_pilot_is_opt_in_and_enforces_the_published_modes(monkeypatch, tmp_path):
    client = TestClient(app)
    monkeypatch.delenv('REGOLITH_JEZERO_PILOT_DIR', raising=False)
    endpoint = '/api/similarity/jezero-pilot'
    assert client.get(endpoint).status_code == 503
    monkeypatch.setenv('REGOLITH_JEZERO_PILOT_DIR', str(tmp_path))
    report = {
        'format': 'jezero-multivista-v1', 'version': 'jezero-r3-test', 'status': 'experimental',
        'reference': {'id': 'jezero'}, 'profile': 'test', 'coverage': {'windows': 2},
        'weights': {'topografia': .75, 'espectral': .25},
        'rankings': {'combined': [{'region_id': 'A'}], 'topography': [{'region_id': 'B'}]},
        **{k: {'pass': True} for k in ('support', 'relevance', 'retrieval', 'stability')},
    }
    file = tmp_path / 'jezero.json'
    file.write_text(json.dumps(report | {'relevance': {'pass': False}}))
    assert client.get(endpoint).status_code == 503
    file.write_text(json.dumps(report))
    assert client.get(endpoint).json()['weights']['espectral'] == .25
    assert client.get(endpoint, params={'mode': 'topography'}).json()['weights'] == {'topografia': 1}
    assert client.get(endpoint, params={'mode': 'invalid'}).status_code == 422
