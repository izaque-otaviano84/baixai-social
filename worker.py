"""Isolate media processing and restrict outbound connections to public HTTPS."""
import ipaddress
import resource
import socket
import sys
from pathlib import Path

from app import MAX_FILE_BYTES, download_to_folder
from yt_dlp.utils import DownloadError


def public_endpoint(address):
    host, port = address[:2]
    ip = ipaddress.ip_address(host)
    ip = getattr(ip, "ipv4_mapped", None) or ip
    return port == 443 and ip.is_global and not ip.is_multicast


def restrict_network():
    # Inspect the numeric destination at connect time, after DNS resolution.
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def checked_connect(sock, address):
        if not public_endpoint(address):
            raise OSError("Destino de rede não autorizado")
        return original_connect(sock, address)

    def checked_connect_ex(sock, address):
        if not public_endpoint(address):
            raise OSError("Destino de rede não autorizado")
        return original_connect_ex(sock, address)

    socket.socket.connect = checked_connect
    socket.socket.connect_ex = checked_connect_ex


if __name__ == "__main__":
    restrict_network()
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_FILE_BYTES, MAX_FILE_BYTES))
    url, output_format, folder = sys.argv[1:]
    try:
        download_to_folder(url, output_format, Path(folder))
    except DownloadError as error:
        detail = str(error).lower()
        sys.exit(3 if "10 minutos" in detail or "40 mib" in detail else 2)
