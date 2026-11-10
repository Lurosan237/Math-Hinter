"""POST /api/review: the live tutor on Vercel. The logic is in src/mathhinter/web.py."""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mathhinter.web import BadRequest, Service, read_request  # noqa: E402

SERVICE = Service(json.loads((ROOT / "site/data/corpus.json").read_text(encoding="utf-8"))["units"],
                  site_key=os.environ.get("GROQ_API_KEY", ""))  # no cache: the site keeps nothing
MAX_BODY = 20_000


class handler(BaseHTTPRequestHandler):  # noqa: N801 (the name Vercel looks for)
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("content-length") or 0)
        if length > MAX_BODY:
            return self._send(413, {"error": "La requête est trop longue.", "code": "size"})
        try:
            request = read_request(self.rfile.read(length))
        except BadRequest as error:
            return self._send(400, {"error": str(error), "code": "input"})
        address = (self.headers.get("x-forwarded-for") or self.client_address[0]).split(",")[0].strip()
        status, body = SERVICE.review(request, address)
        self._send(status, body)

    def do_GET(self):  # noqa: N802
        self._send(200, {"ok": True, "site_key": bool(SERVICE.site_key), "passages": len(SERVICE.units)})

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
