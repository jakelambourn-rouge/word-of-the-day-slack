#!/usr/bin/env python3
"""
Posts a Word of the Day to Slack via Incoming Webhook.

Sources:
- Random word: https://random-word-api.herokuapp.com/word?number=1
- Definitions: https://api.dictionaryapi.dev/api/v2/entries/en/<word>

Env:
- SLACK_WEBHOOK_URL: your Slack Incoming Webhook URL
"""

import json
import os
import random
import re
from urllib.request import urlopen, Request
from urllib.error import URLError
from urllib.parse import quote

SLACK_WEBHOOK_URL = os.environ["SLACK_WEBHOOK_URL"]
HEADERS = {"User-Agent": "wotd-bot/1.0"}

# ---------------------------------------------------------------------------

def fetch(url: str) -> str | None:
    """Fetch text from URL or return None on error."""
    try:
        with urlopen(Request(url, headers=HEADERS), timeout=12) as r:
            return r.read().decode("utf-8")
    except URLError:
        return None

def mrkdwn_escape(s: str) -> str:
    """Escape Slack mrkdwn special chars so plain text stays plain."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

TAG_RE = re.compile(r"<[^>]+>")
URL_RE = re.compile(r"https?://\S+")

def clean_text(s: str) -> str:
    """Remove HTML tags/URLs and compress whitespace."""
    s = TAG_RE.sub("", s)
    s = URL_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

# ---------------------------------------------------------------------------

def get_random_word() -> str:
    data = fetch("https://random-word-api.herokuapp.com/word?number=1")
    if data:
        try:
            w = json.loads(data)[0]
            return str(w).strip()
        except Exception:
            pass
    # Fallback list of safe, recognisable words
    fallback = [
        "serendipity","parsimonious","pellucid","obdurate","ephemeral",
        "ameliorate","cacophony","loquacious","incisive","salubrious",
        "winsome","evanescent","truculent","cogent","sagacious",
    ]
    return random.choice(fallback)

def tidy_definitions(entries: list) -> list[str]:
    defs: list[str] = []
    for e in entries:
        for m in e.get("meanings", []):
            pos = m.get("partOfSpeech", "")
            for d in m.get("definitions", []):
                defi = d.get("definition")
                if not defi:
                    continue
                line = f"{pos}: {defi}" if pos else str(defi)
                line = clean_text(line)
                if line:
                    defs.append(line)
    # de-dup, keep first 3, cap length
    out, seen = [], set()
    for d in defs:
        if d in seen:
            continue
        seen.add(d)
        out.append(d[:240])
        if len(out) >= 3:
            break
    return out

def get_definitions(word: str) -> list[str]:
    data = fetch(f"https://api.dictionaryapi.dev/api/v2/entries/en/{quote(word)}")
    if not data:
        return []
    try:
        parsed = json.loads(data)
        if isinstance(parsed, list):
            return tidy_definitions(parsed)
    except Exception:
        pass
    return []

# ---------------------------------------------------------------------------

def post_to_slack(text: str, blocks: list | None = None) -> None:
    payload = {"text": text}
    if blocks:
        payload["blocks"] = blocks
    req = Request(
        SLACK_WEBHOOK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=12) as r:
        r.read()

# ---------------------------------------------------------------------------

def main() -> None:
    word = get_random_word()
    defs = get_definitions(word)
    wiktionary = f"https://en.wiktionary.org/wiki/{quote(word)}"

    title = f"*Word of the day*: *{mrkdwn_escape(word)}*"

    if defs:
        safe_defs = [mrkdwn_escape(d) for d in defs]
        bullet = "\n".join(f"• {d}" for d in safe_defs)
        text = f"{title}\n{bullet}"
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": title}},
            {"type": "section", "text": {"type": "mrkdwn", "text": bullet}},
            {"type": "context", "elements": [
                {"type": "mrkdwn", "text": f"<{wiktionary}|More on Wiktionary>"}
            ]},
        ]
    else:
        text = f"{title}\nNo definition found."
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": title}},
            {"type": "context", "elements": [
                {"type": "mrkdwn", "text": f"<{wiktionary}|Wiktionary>"}
            ]},
        ]

    post_to_slack(text, blocks)

# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
