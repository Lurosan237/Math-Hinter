"""POST /api/transcribe: read photographed pages into text. The logic is in src/mathhinter/web.py."""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mathhinter.web import PhotoService  # noqa: E402

SERVICE = PhotoService(site_key=os.environ.get("GROQ_API_KEY", ""))
MAX_BODY = 4_400_000  # under Vercel's 4.5 MB request limit


class handler(BaseHTTPRequestHandler):  # noqa: N801 (the name Vercel looks for)
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("content-length") or 0)
        if length > MAX_BODY:
            return self._send(413, {"error": "Les photos sont trop lourdes.", "code": "size"})
        address = (self.headers.get("x-forwarded-for") or self.client_address[0]).split(",")[0].strip()
        status, body = SERVICE.read_photos(self.rfile.read(length), address)
        self._send(status, body)

    def _send(self, status: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # requests carry students' work and maybe a key: nothing is logged
        pass
