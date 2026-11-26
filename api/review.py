"""POST /api/review: the live tutor on Vercel. The logic is in src/mathhinter/web.py.

POST /api/review           one review, as JSON; with "stream": true, its steps as they happen, one JSON per line
POST /api/review?hint=1    the next, more explicit hint for a flagged line
POST /api/review?similar=1 a similar exercise, its checked answer sealed; ?answer=1 checks the student's answer
POST /api/review?explain=1 one turn of "Explique-moi" about the flagged line
"""

import json
import os
import queue
import sys
import threading
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
        body = self.rfile.read(length)
        address = (self.headers.get("x-forwarded-for") or self.client_address[0]).split(",")[0].strip()
        if "hint=1" in self.path:
            return self._send(*SERVICE.hint(body, address))
        if "similar=1" in self.path:
            return self._send(*SERVICE.similar(body, address))
        if "answer=1" in self.path:
            return self._send(*SERVICE.answer(body))
        if "explain=1" in self.path:
            return self._send(*SERVICE.explain(body, address))
        try:
            request = read_request(body)
            stream = bool(json.loads(body).get("stream"))
        except BadRequest as error:
            return self._send(400, {"error": str(error), "code": "input"})
        if not stream:
            return self._send(*SERVICE.review(request, address))
        self._stream(request, address)

    def _stream(self, request: dict, address: str) -> None:
        """Each step as a line of JSON while the review runs, then {"status": ..., "body": ...}."""
        steps: queue.Queue = queue.Queue()
        result: dict = {}

        def run():
            try:
                result["status"], result["body"] = SERVICE.review(request, address, on_step=steps.put)
            except Exception:  # noqa: BLE001 (the visitor gets a message; nothing about their work is logged)
                result["status"], result["body"] = 500, {"error": "La relecture a échoué.", "code": "server"}
            steps.put(None)

        threading.Thread(target=run, daemon=True).start()
        self.send_response(200)
        self.send_header("content-type", "application/x-ndjson; charset=utf-8")
        self.send_header("cache-control", "no-store")
        self.send_header("x-accel-buffering", "no")
        self.end_headers()
        while (step := steps.get()) is not None:
            self._line({"step": step})
        self._line({"status": result["status"], "body": result["body"]})

    def _line(self, data: dict) -> None:
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8") + b"\n")
        self.wfile.flush()

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
