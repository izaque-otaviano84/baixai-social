"""Aplicativo simples para baixar vídeos públicos autorizados do Instagram/TikTok."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import re
import shutil
import tempfile
from pathlib import Path
from threading import BoundedSemaphore, Lock
from time import monotonic
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

import yt_dlp
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, ValidationError
from yt_dlp.utils import DownloadError

ROOT = Path(__file__).resolve().parent
MAX_FILE_BYTES = 40 * 1024 * 1024
MAX_DURATION_SECONDS = 10 * 60
MAX_REQUEST_URL_LENGTH = 2048
PROCESS_TIMEOUT = int(os.getenv("PROCESS_TIMEOUT_SECONDS", "90"))
_DOWNLOAD_LOCK = BoundedSemaphore(1)
_RATE_LOCK = Lock()
_attempts: dict[str, list[float]] = {}


def enforce_rate_limit(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    now = monotonic()
    with _RATE_LOCK:
        for key, timestamps in list(_attempts.items()):
            recent = [stamp for stamp in timestamps if now - stamp < 60]
            if recent:
                _attempts[key] = recent
            else:
                del _attempts[key]
        timestamps = _attempts.setdefault(client, [])
        if len(timestamps) >= 4 or sum(map(len, _attempts.values())) >= 20:
            raise HTTPException(429, "Limite de tentativas atingido. Aguarde um minuto.")
        timestamps.append(now)

app = FastAPI(title="Baixaí", docs_url=None, redoc_url=None, openapi_url=None)


class DownloadInput(BaseModel):
    url: str = Field(min_length=12, max_length=MAX_REQUEST_URL_LENGTH)
    format: Literal["mp4", "mp3"]


def validate_video_url(raw: str) -> str:
    """Aceita somente URLs HTTPS de vídeos do Instagram ou TikTok."""
    try:
        parts = urlsplit(raw.strip())
        host = (parts.hostname or "").lower().rstrip(".")
        # Subdomínios não autorizados e URLs com credenciais são rejeitados.
        if parts.scheme.lower() != "https" or parts.username is not None or parts.password is not None or parts.port is not None or parts.netloc.lower() != host:
            raise ValueError("URL inválida")
        if host not in {
            "instagram.com", "www.instagram.com", "m.instagram.com",
            "tiktok.com", "www.tiktok.com", "m.tiktok.com",
            "vm.tiktok.com", "vt.tiktok.com",
        }:
            raise ValueError("Plataforma não suportada")
        path = parts.path or "/"
        if host.endswith("instagram.com") and not re.match(r"^/(reel|reels|p|tv)/[A-Za-z0-9_.-]+/?$", path, re.I):
            raise ValueError("Cole o link direto de um Reels ou publicação com vídeo")
        if host.endswith("tiktok.com") and host not in {"vm.tiktok.com", "vt.tiktok.com"}:
            if not (re.match(r"^/@[A-Za-z0-9_.-]+/video/\d+/?$", path, re.I)
                    or re.match(r"^/t/[A-Za-z0-9_.-]+/?$", path, re.I)
                    or re.match(r"^/video/\d+/?$", path, re.I)):
                raise ValueError("Cole o link direto de um vídeo do TikTok")
        if host in {"vm.tiktok.com", "vt.tiktok.com"} and not re.fullmatch(r"/[A-Za-z0-9]+/?", path):
            raise ValueError("Cole um link de vídeo, não de perfil")
        # Nunca enviar fragmentos ou parâmetros de autenticacão no link.
        return urlunsplit(("https", host, path, "", ""))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "Link inválido") from exc


def enforce_video_limits(info: dict, *, incomplete: bool = False) -> str | None:
    """Impedir uso excessivo do espaço/transferência da hospedagem grátis."""
    duration = info.get("duration")
    if duration and duration > MAX_DURATION_SECONDS:
        return "Este vídeo ultrapassa o limite de 10 minutos."
    size = info.get("filesize") or info.get("filesize_approx")
    if size and size > MAX_FILE_BYTES:
        return "Este vídeo ultrapassa o limite de 40 MiB."
    if info.get("is_live"):
        return "Lives não são suportadas."
    return None


def make_progress_hook():
    def hook(data: dict) -> None:
        if data.get("status") == "downloading" and data.get("downloaded_bytes", 0) > MAX_FILE_BYTES:
            raise DownloadError("Este vídeo ultrapassa o limite de 40 MiB.")
    return hook


def download_to_folder(url: str, output_format: str, folder: Path) -> Path:
    common = {
        "outtmpl": str(folder / "arquivo.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": False,
        "max_filesize": MAX_FILE_BYTES,
        "match_filter": enforce_video_limits,
        "progress_hooks": [make_progress_hook()],
        "socket_timeout": 12,
        "proxy": "",
        "allowed_extractors": ["Instagram", "TikTok", "TikTokVM"],
        "extract_flat": "in_playlist",
        "retries": 2,
        "fragment_retries": 2,
        "concurrent_fragment_downloads": 1,
    }
    if output_format == "mp3":
        common.update({
            "format": "bestaudio[protocol=https]/best[protocol=https]",
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
            ],
        })
    else:
        common.update({
            "format": "b[ext=mp4][protocol=https]/b[protocol=https]",
            "merge_output_format": "mp4",
            "postprocessors": [
                {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}
            ],
        })

    with yt_dlp.YoutubeDL(common) as downloader:
        info = downloader.extract_info(url, download=False)
        if not info or info.get("_type") in {"playlist", "multi_video"}:
            raise DownloadError("Envie o link de uma publicação com um único vídeo.")
        downloader.process_info(info)

    matches = list(folder.glob(f"*.{output_format}"))
    if not matches:
        raise DownloadError("Não foi possível gerar o arquivo no formato escolhido.")
    result = max(matches, key=lambda p: p.stat().st_size)
    if result.stat().st_size > MAX_FILE_BYTES:
        raise DownloadError("O arquivo final ultrapassa o limite de 40 MiB.")
    return result


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(ROOT / "static" / "index.html", media_type="text/html")


@app.get("/styles.css", include_in_schema=False)
def styles():
    return FileResponse(ROOT / "static" / "styles.css", media_type="text/css")


@app.get("/script.js", include_in_schema=False)
def script():
    return FileResponse(ROOT / "static" / "script.js", media_type="application/javascript")


class TemporaryDownload(FileResponse):
    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            shutil.rmtree(Path(self.path).parent, ignore_errors=True)
            _DOWNLOAD_LOCK.release()


def run_worker(url: str, output_format: str, folder: Path) -> None:
    with subprocess.Popen(
        [sys.executable, str(ROOT / "worker.py"), url, output_format, str(folder)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    ) as process:
        try:
            status = process.wait(timeout=PROCESS_TIMEOUT)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            raise HTTPException(504, "O vídeo demorou demais para ser processado. Tente um vídeo mais curto.")
        if status == 3:
            raise HTTPException(422, "O vídeo ultrapassa o limite de 10 minutos ou 40 MiB.")
        if status != 0:
            raise HTTPException(422, "A plataforma pode ter restringido o acesso. Confira se o vídeo é público e tente outro link.")


@app.post("/api/download")
async def download(request: Request):
    enforce_rate_limit(request)
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 4096:
            raise HTTPException(413, "O link enviado é grande demais.")
        body.extend(chunk)
    try:
        payload = DownloadInput.model_validate_json(body)
    except ValidationError:
        raise HTTPException(422, "Envie um link válido e escolha MP4 ou MP3.") from None
    url = validate_video_url(payload.url)
    return await run_in_threadpool(prepare_download, url, payload.format)


def prepare_download(url: str, output_format: str):
    if not _DOWNLOAD_LOCK.acquire(blocking=False):
        raise HTTPException(429, "Já existe um download em andamento. Tente novamente em instantes.")

    folder = None
    try:
        folder = Path(tempfile.mkdtemp(prefix="baixai-"))
        run_worker(url, output_format, folder)
        result = folder / f"arquivo.{output_format}"
        if not result.is_file() or not 0 < result.stat().st_size <= MAX_FILE_BYTES:
            raise HTTPException(422, "Não foi possível gerar o arquivo dentro do limite de 40 MiB.")
        return TemporaryDownload(
            result,
            media_type="audio/mpeg" if output_format == "mp3" else "video/mp4",
            filename=f"baixai.{output_format}",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )
    except BaseException:
        if folder is not None:
            shutil.rmtree(folder, ignore_errors=True)
        _DOWNLOAD_LOCK.release()
        raise
