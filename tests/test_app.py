"""Testes locais sem dependência de rede externa ou cookies reais."""
import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app as module

client = TestClient(module.app)

@pytest.fixture(autouse=True)
def clear_rate_limit_between_tests():
    with module._RATE_LOCK:
        module._attempts.clear()
    yield
    with module._RATE_LOCK:
        module._attempts.clear()

KEY = "k" * 40
COOKIES = ("# Netscape HTTP Cookie File\n"
           ".tiktok.com\tTRUE\t/\tTRUE\t1893456000\tsessionid\ttoken-ficticio\n"
           ".instagram.com\tTRUE\t/\tTRUE\t1893456000\tsessionid\tnao-exportar\n")


@pytest.mark.parametrize("url", [
    "https://www.instagram.com/reel/C9aBcde/",
    "https://www.instagram.com/p/C9aBcde/",
    "https://www.tiktok.com/@username/video/789456123",
    "https://vm.tiktok.com/ZMdexample/",
    "https://vt.tiktok.com/ZMdexample/",
])
def test_supported_urls(url):
    assert module.validate_video_url(url) == url


@pytest.mark.parametrize("url", [
    "https://attacker.example/path", "http://www.instagram.com/reel/abc/",
    "https://instagram.com.evil.example/reel/abc/", "https://www.instagram.com/",
    "https://www.instagram.com/example/", "https://www.tiktok.com/@someone",
    "https://admin:password@www.instagram.com/reel/abc/",
    "https://www.instagram.com:8080/reel/abc/", "https://vt.tiktok.com/foo/bar/",
    "https://www.tiktok.com/@user/video/123?redirect=http://127.0.0.1",
])
def test_invalid_urls(url):
    if "?redirect=" in url:
        assert "redirect" not in module.validate_video_url(url)
    else:
        with pytest.raises(module.HTTPException) as exc:
            module.validate_video_url(url)
        assert exc.value.status_code == 400


def test_home_and_assets():
    assert client.get("/health").json() == {"ok": True}
    assert "Baixe seu vídeo." in client.get("/").text
    assert "private-key" not in client.get("/").text
    assert "paste-button" in client.get("/").text
    assert client.get("/styles.css").status_code == 200
    assert client.get("/script.js").status_code == 200


def test_download_and_cleanup(monkeypatch):
    saved = []
    def fake_download(url: str, fmt: str, folder: Path, *, private: bool = False):
        saved.append((folder, private))
        (folder / f"arquivo.{fmt}").write_bytes(b"fake video")
    monkeypatch.setattr(module, "run_worker", fake_download)
    response = client.post("/api/download", json={
        "url": "https://www.instagram.com/reel/test/", "format": "mp4"
    })
    assert response.status_code == 200
    assert response.content == b"fake video"
    assert response.headers["cache-control"] == "no-store"
    assert saved and saved[0][1] is False and not saved[0][0].exists()


def test_private_not_configured(monkeypatch):
    monkeypatch.delenv("PRIVATE_DOWNLOAD_KEY", raising=False)
    monkeypatch.delenv("TIKTOK_COOKIES_BASE64", raising=False)
    response = client.post("/api/download", json={
        "url": "https://www.tiktok.com/@test/video/123", "format": "mp4", "private": True
    })
    assert response.status_code == 503


def test_admin_required_and_wrong_key(monkeypatch):
    monkeypatch.setenv("PRIVATE_DOWNLOAD_KEY", KEY)
    monkeypatch.setenv("TIKTOK_COOKIES_BASE64", base64.b64encode(COOKIES.encode()).decode())
    for headers in ({}, {"X-Baixai-Admin-Key": "senha-errada"}):
        result = client.post("/api/download", json={
            "url": "https://www.tiktok.com/@test/video/123", "format": "mp4", "private": True
        }, headers=headers)
        assert result.status_code == 401


def test_private_only_tiktok(monkeypatch):
    monkeypatch.setenv("PRIVATE_DOWNLOAD_KEY", KEY)
    monkeypatch.setenv("TIKTOK_COOKIES_BASE64", base64.b64encode(COOKIES.encode()).decode())
    result = client.post("/api/download", json={
        "url": "https://www.instagram.com/reel/abc/", "format": "mp4", "private": True
    }, headers={"X-Baixai-Admin-Key": KEY})
    assert result.status_code == 400


def test_private_success(monkeypatch):
    monkeypatch.setenv("PRIVATE_DOWNLOAD_KEY", KEY)
    monkeypatch.setenv("TIKTOK_COOKIES_BASE64", base64.b64encode(COOKIES.encode()).decode())
    seen = []
    def fake_download(url: str, fmt: str, folder: Path, *, private: bool = False):
        seen.append((folder, private))
        (folder / f"arquivo.{fmt}").write_bytes(b"fake private")
    monkeypatch.setattr(module, "run_worker", fake_download)
    response = client.post("/api/download", json={
        "url": "https://www.tiktok.com/@test/video/123", "format": "mp4", "private": True
    }, headers={"X-Baixai-Admin-Key": KEY})
    assert response.status_code == 200
    assert seen and seen[0][1] is True and not seen[0][0].exists()


def test_cookie_filter_and_file_permissions(monkeypatch, tmp_path):
    monkeypatch.setenv("TIKTOK_COOKIES_BASE64", base64.b64encode(COOKIES.encode()).decode())
    path = module.write_session_cookies(tmp_path)
    assert path.stat().st_mode & 0o777 == 0o600
    assert b"token-ficticio" in path.read_bytes()
    assert b"nao-exportar" not in path.read_bytes()
    path.unlink()


def test_public_never_uses_cookiefile(monkeypatch, tmp_path):
    monkeypatch.setenv("TIKTOK_COOKIES_BASE64", base64.b64encode(COOKIES.encode()).decode())
    captured = []
    class FakeYtDlp:
        def __init__(self, opts): captured.append(opts)
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def extract_info(self, url, download=False): return {"duration": 6, "id": "123"}
        def process_info(self, info): (tmp_path / "arquivo.mp4").write_bytes(b"fake")
    monkeypatch.setattr(module.yt_dlp, "YoutubeDL", FakeYtDlp)
    module.download_to_folder("https://www.tiktok.com/@test/video/123", "mp4", tmp_path)
    assert "cookiefile" not in captured[0]


def test_worker_restricts_private_addresses():
    from worker import public_endpoint
    for addr in [("127.0.0.1", 443), ("169.254.169.254", 443), ("10.0.0.1", 443),
                 ("::ffff:127.0.0.1", 443, 0, 0), ("8.8.8.8", 80)]:
        assert not public_endpoint(addr)
    assert public_endpoint(("8.8.8.8", 443))


def test_request_body_limit():
    response = client.post("/api/download", content=b"x" * 4097)
    assert response.status_code == 413


def test_rate_limit():
    with TestClient(module.app, client=("rate-test", 50000)) as isolated:
        for _ in range(4):
            assert isolated.post("/api/download", json={}).status_code == 422
        assert isolated.post("/api/download", json={}).status_code == 429
