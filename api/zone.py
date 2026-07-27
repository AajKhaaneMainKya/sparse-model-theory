from __future__ import annotations

import json
import os
from urllib import error, request

from engine.retrieval import Match


OLLAMA_URL = "http://localhost:11434/v1/chat/completions"
DEFAULT_OLLAMA_MODEL = "qwen2.5:7b-instruct-q4_K_M"
OLLAMA_MODEL = os.environ.get("SMT_ZONE_MODEL", DEFAULT_OLLAMA_MODEL)
SYSTEM_PROMPT = (
    "You are not Rahul's identity or authority over him. You are a judgment-preserving tool "
    "that surfaces his own prior reasoning. Do not tell him what to do — reflect his own "
    "precedent back to him and let him decide. End every answer with a reflective question, "
    "not a statement."
)


def answer_with_context(query: str, matches: list[Match]) -> str:
    top_matches = matches[:1]
    context = "\n\n".join(
        f"Prior precedent from Rahul's own history #{index}\n"
        f"Title: {match.note.title}\n"
        f"Body:\n{match.note.body}"
        for index, match in enumerate(top_matches, start=1)
    )

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "User query:\n"
                    f"{query}\n\n"
                    "Context below is prior precedent from Rahul's own history, not general knowledge.\n\n"
                    f"{context}\n\n"
                    "Reflect the relevant precedent back compactly. Do not give commands or decide for Rahul."
                ),
            },
        ],
        "temperature": 0.2,
        "stream": False,
    }

    encoded = json.dumps(payload).encode("utf-8")
    http_request = request.Request(
        OLLAMA_URL,
        data=encoded,
        headers={"content-type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(http_request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return f"Zone unavailable: Ollama returned HTTP {exc.code}: {detail}"
    except error.URLError as exc:
        return f"Zone unavailable: could not connect to Ollama at {OLLAMA_URL}: {exc.reason}"
    except TimeoutError:
        return "Zone unavailable: Ollama request timed out."
    except OSError as exc:
        return f"Zone unavailable: Ollama request failed: {exc}"

    try:
        return str(data["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError) as exc:
        return f"Zone unavailable: unexpected Ollama response shape: {exc}"
