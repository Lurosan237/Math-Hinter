import io
import json
import subprocess
import urllib.error
from pathlib import Path

import pytest

from mathhinter.llm.client import Client, LLMError, cache_key, read_env

ROOT = Path(__file__).parent.parent
KEY = "secret-key"
MESSAGES = [{"role": "user", "content": "bonjour"}]


class Fake:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return io.BytesIO(json.dumps(outcome).encode())


def http_error(code, body=b"nope", headers=None):
    return urllib.error.HTTPError("https://x", code, "error", headers or {}, io.BytesIO(body))


def client(fake, **kwargs):
    return Client(KEY, opener=fake, sleep=lambda _: None, **kwargs)


def test_second_identical_request_comes_from_the_cache(tmp_path):
    fake = Fake({"choices": [{"message": {"content": "salut"}}]})
    c = client(fake, cache_dir=tmp_path)
    first, second = c.chat("m", MESSAGES), c.chat("m", MESSAGES)
    assert first == second and len(fake.requests) == 1


def test_any_change_to_the_request_misses_the_cache():
    base = {"model": "m", "messages": MESSAGES, "temperature": 0.0}
    assert cache_key(base) != cache_key({**base, "model": "n"})


def test_cache_never_holds_the_key(tmp_path):
    client(Fake({"ok": 1}), cache_dir=tmp_path).chat("m", MESSAGES)
    assert KEY not in next(tmp_path.iterdir()).read_text()


def test_rate_limit_is_retried():
    fake = Fake(http_error(429, headers={"retry-after": "1"}), {"ok": 1})
    assert client(fake).chat("m", MESSAGES) == {"ok": 1}


def test_bad_key_fails_at_once_without_showing_it():
    fake = Fake(http_error(401, body=f"bad {KEY}".encode()))
    with pytest.raises(LLMError) as error:
        client(fake).chat("m", MESSAGES)
    assert KEY not in str(error.value) and len(fake.requests) == 1


def test_request_names_the_client():
    fake = Fake({"data": [{"id": "b"}, {"id": "a"}]})
    assert client(fake).models() == ["a", "b"]
    assert fake.requests[0].get_header("User-agent") == "math-hinter/0.1"


def test_key_is_not_in_the_client_repr():
    assert KEY not in repr(client(Fake()))


def test_env_file_from_notepad_is_read(tmp_path):
    path = tmp_path / ".env"
    path.write_bytes(b'\xef\xbb\xbfGROQ_API_KEY="abc"\n# note\n')
    assert read_env(path) == {"GROQ_API_KEY": "abc"}
    assert read_env(tmp_path / "missing") == {}


def test_env_file_is_ignored_by_git():
    assert subprocess.run(["git", "check-ignore", ".env"], cwd=ROOT, capture_output=True).returncode == 0
