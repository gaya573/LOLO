from __future__ import annotations

import io
import json
import random
import socket
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from PIL import ImageGrab

from .discovery import find_local_ipv4s


ASSIST_PORT = 18766


@dataclass(frozen=True)
class RemoteAssistInfo:
    code: str
    name: str
    host: str
    port: int = ASSIST_PORT

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def screenshot_url(self) -> str:
        return f"{self.base_url}/screenshot.png?code={self.code}"


class RemoteAssistServer:
    def __init__(self) -> None:
        self.code = f"{random.randint(100000, 999999)}"
        self.name = socket.gethostname()
        self.host = _best_local_ip()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def info(self) -> RemoteAssistInfo:
        return RemoteAssistInfo(code=self.code, name=self.name, host=self.host)

    def start(self) -> RemoteAssistInfo:
        if self._server:
            return self.info

        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - http.server API
                path, _, query = self.path.partition("?")
                if parse_qs(query).get("code") != [owner.code]:
                    self.send_response(403)
                    self.end_headers()
                    return
                if path == "/info":
                    self._send_json(
                        {
                            "name": owner.name,
                            "host": owner.host,
                            "port": ASSIST_PORT,
                            "code": owner.code,
                            "screenshot_url": owner.info.screenshot_url,
                        }
                    )
                    return
                if path == "/screenshot.png":
                    self._send_screenshot()
                    return
                self.send_response(404)
                self.end_headers()

            def _send_json(self, data: dict[str, object]) -> None:
                body = json.dumps(data).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_screenshot(self) -> None:
                image = ImageGrab.grab()
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                body = buffer.getvalue()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        self._server = ThreadingHTTPServer(("0.0.0.0", ASSIST_PORT), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self.info

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            self._thread = None


def _best_local_ip() -> str:
    ips = find_local_ipv4s()
    return ips[0] if ips else "127.0.0.1"
