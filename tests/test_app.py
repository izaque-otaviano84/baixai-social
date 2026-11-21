"""Testes básicos. Rodar: pytest -q (após instalar requirements e pytest/httpx)."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app as module

client = TestClient(module.app)


@pytest.mark.parametrize('url', [
    'https://www.instagram.com/reel/C9aBcde/',
    'https://www.instagram.com/p/C9aBcde/',
    'https://www.tiktok.com/@username/video/789456123',
    'https://vm.tiktok.com/ZMdexample/',
    'https://vt.tiktok.com/ZMdexample/',
])
def test_supported_video_urls(url):
    assert module.validate_video_url(url) == url


@pytest.mark.parametrize('url', [
    'https://attacker.example/path',
    'http://www.instagram.com/reel/abc/',
    'https://instagram.com.evil.example/reel/abc/',
    'https://www.instagram.com/',
    'https://www.instagram.com/example/',
    'https://www.tiktok.com/@someone',
    'https://evil.com/?link=instagram.com',
    'https://admin:password@www.instagram.com/reel/abc/',
    'https://www.instagram.com:8080/reel/abc/',
])
def test_invalid_urls(url):
    with pytest.raises(module.HTTPException) as exc:
        module.validate_video_url(url)
    assert exc.value.status_code == 400


def test_home_and_health():
    assert client.get('/').status_code == 200
    assert 'Baixar agora' in client.get('/').text
    assert client.get('/health').json() == {'ok': True}
    assert client.get('/styles.css').status_code == 200
    assert client.get('/script.js').status_code == 200


def test_download_success_and_file_cleanup(monkeypatch):
    saved = []

    def fake_download(url: str, fmt: str, folder: Path) -> None:
        saved.append(folder)
        path = folder / ('arquivo.' + fmt)
        path.write_bytes(b'fake mp4 file')

    monkeypatch.setattr(module, 'run_worker', fake_download)
    response = client.post('/api/download', json={
        'url': 'https://www.instagram.com/reel/test/', 'format': 'mp4'
    })
    assert response.status_code == 200
    assert response.content == b'fake mp4 file'
    assert 'attachment' in response.headers['content-disposition']
    assert saved and not saved[0].exists()


def test_bad_format_rejected():
    response = client.post('/api/download', json={
        'url': 'https://www.instagram.com/reel/test/', 'format': 'exe'
    })
    assert response.status_code == 422


def test_url_strips_parameters_and_fragment():
    url = 'https://www.instagram.com/reel/C9aBcde/?igsh=token#fragment'
    assert module.validate_video_url(url) == 'https://www.instagram.com/reel/C9aBcde/'


@pytest.mark.parametrize('address', [
    ('127.0.0.1', 443),
    ('169.254.169.254', 443),
    ('10.0.0.1', 443),
    ('::ffff:127.0.0.1', 443, 0, 0),
    ('224.0.0.1', 443),
    ('8.8.8.8', 80),
])
def test_worker_blocks_connect_destination(address):
    from worker import public_endpoint
    assert not public_endpoint(address)


def test_worker_allows_public_tls():
    from worker import public_endpoint
    assert public_endpoint(('8.8.8.8', 443))


def test_request_body_limit():
    response = client.post('/api/download', content=b'x' * 4097)
    assert response.status_code == 413


def test_rate_limit():
    with TestClient(module.app, client=('rate-test', 50000)) as isolated_client:
        for _ in range(4):
            assert isolated_client.post('/api/download', json={}).status_code == 422
        assert isolated_client.post('/api/download', json={}).status_code == 429
