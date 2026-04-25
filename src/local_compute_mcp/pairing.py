from __future__ import annotations

import json
import random
import socket
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .discovery import find_local_ipv4s


PAIRING_PORT = 18765


@dataclass(frozen=True)
class PairingInfo:
    code: str
    name: str
    host: str
    port: int = PAIRING_PORT


class PairingServer:
    def __init__(self) -> None:
        self.code = f"{random.randint(100000, 999999)}"
        self.name = socket.gethostname()
        self.host = _best_local_ip()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def info(self) -> PairingInfo:
        return PairingInfo(code=self.code, name=self.name, host=self.host)

    def start(self) -> PairingInfo:
        if self._server:
            return self.info

        payload = {
            "code": self.code,
            "name": self.name,
            "host": self.host,
            "port": PAIRING_PORT,
        }

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - http.server API
                if self.path != "/pair-info":
                    self.send_response(404)
                    self.end_headers()
                    return
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        self._server = ThreadingHTTPServer(("0.0.0.0", PAIRING_PORT), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self.info

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            self._thread = None


def find_pairing_code(code: str, timeout_sec: float = 0.35) -> PairingInfo | None:
    import urllib.request

    code = code.strip()
    if not code:
        return None

    for local_ip in find_local_ipv4s():
        prefix = ".".join(local_ip.split(".")[:3])
        for last in range(1, 255):
            host = f"{prefix}.{last}"
            url = f"http://{host}:{PAIRING_PORT}/pair-info"
            try:
                with urllib.request.urlopen(url, timeout=timeout_sec) as response:
                    data = json.loads(response.read().decode("utf-8"))
            except Exception:
                continue
            if str(data.get("code")) == code:
                return PairingInfo(
                    code=str(data.get("code")),
                    name=str(data.get("name") or f"pc-{last}"),
                    host=str(data.get("host") or host),
                    port=int(data.get("port") or PAIRING_PORT),
                )
    return None


def _best_local_ip() -> str:
    ips = find_local_ipv4s()
    return ips[0] if ips else "127.0.0.1"
