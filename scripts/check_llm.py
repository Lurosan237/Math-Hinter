"""Test the connection to Groq from this computer. Run it with: python scripts/check_llm.py

It asks for your API key the first time and saves it in .env, which git ignores. It sends only a made-up question,
and writes the result without the key to data/private/llm_check.json.
"""

import getpass
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mathhinter.llm.client import Client, LLMError, read_env  # noqa: E402

ENV = ROOT / ".env"
QUESTION = "Une suite strictement positive peut-elle valoir 0 ? Réponds en une phrase, en français."
PREFERRED = ("llama-3.3-70b-versatile", "openai/gpt-oss-120b", "llama-3.1-8b-instant")


def get_key() -> str:
    key = read_env(ENV).get("GROQ_API_KEY", "")
    if key:
        return key
    print("Paste your Groq API key and press Enter. Nothing will show as you paste.")
    key = getpass.getpass("Key: ").strip()
    if not key:
        sys.exit("No key entered.")
    with ENV.open("a", encoding="utf-8") as handle:
        handle.write(f"GROQ_API_KEY={key}\n")
    print(f"Saved in {ENV}")
    return key


def main() -> None:
    client = Client(get_key())
    result: dict = {"ok": False, "checked_at": time.strftime("%Y-%m-%d %H:%M")}
    try:
        models = client.models()
        result["models"] = models
        model = next((m for m in PREFERRED if m in models), models[0])
        started = time.time()
        reply = client.chat(model, [{"role": "user", "content": QUESTION}], max_tokens=120)
        result.update(ok=True, model=model, seconds=round(time.time() - started, 1),
                      answer=reply["choices"][0]["message"]["content"], usage=reply.get("usage"))
        print(f"\nIt works. {len(models)} models available. Tried {model}:\n{result['answer']}\n")
    except LLMError as error:
        result["error"] = str(error)
        print(f"\nIt didn't work: {error}\n")
    target = ROOT / "data" / "private" / "llm_check.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Now tell Claude it's done.")


if __name__ == "__main__":
    main()
