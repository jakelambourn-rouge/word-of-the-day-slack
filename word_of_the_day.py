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
HEADERS = {"User-Agent": "wotd-bot/1.4"}

# ---------- helpers ----------

def fetch(url: str) -> str | None:
    try:
        with urlopen(Request(url, headers=HEADERS), timeout=12) as r:
            return r.read().decode("utf-8")
    except URLError:
        return None

# Strip HTML tags and URLs, compress whitespace
TAG_RE = re.compile(r"<[^>]+>")
URL_RE = re.compile(r"https?://\S+")
def clean_text(s: str) -> str:
    s = TAG_RE.sub("", s)
    s = URL_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

# ---------- word + defs ----------

def get_random_word() -> str:
    data = fetch("https://random-word-api.herokuapp.com/word?number=1")
    if data:
        try:
            w = json.loads(data)[0]
            return str(w).strip()
        except Exception:
            pass
    # safe fallback list
    fallback = [
        "serendipity","parsimonious","pellucid","obdurate","ephemeral",
        "ameliorate","cacophony","loquacious","incisive","salubrious",
        "winsome","evanescent","truculent","cogent","sagacious",
    ]
    return random.choice(fallback)

def parse_entry(entry: dict) -> tuple[list[str], list[str]]:
    """Return (definitions, synonyms) from a single API entry."""
    defs, syns = [], []
    for meaning in entry.get("meanings", []):
        pos = meaning.get("partOfSpeech", "")
        # Definitions
        for d in meaning.get("definitions", []):
            defi = d.get("definition")
            if defi:
                line = f"{pos}: {defi}" if pos else str(defi)
                line = clean_text(line)
                if line:
                    defs.append(line)
        # Synonyms
        for s in meaning.get("synonyms", []):
            s = clean_text(s)
            if s:
                syns.append(s)
    # de-dup and trim
    defs = list(dict.fromkeys(defs))[:3]
    syns = list(dict.fromkeys(syns))[:6]
    return defs, syns

def get_word_data(word: str) -> tuple[list[str], list[str]]:
    """Return (definitions, synonyms)."""
    data = fetch(f"https://api.dictionaryapi.dev/api/v2/entries/en/{quote(word)}")
    if not data:
        return [], []
    try:
        parsed = json.loads(data)
        if isinstance(parsed, list):
            defs, syns = [], []
            for e in parsed:
                d, s = parse_entry(e)
                defs.extend(d)
                syns.extend(s)
            # de-dup across entries
            defs = list(dict.fromkeys(defs))[:3]
            syns = list(dict.fromkeys(syns))[:6]
            return defs, syns
    except Exception:
        pass
    return [], []

# ---------- slack ----------

def post_to_slack(word: str, defs: list[str], syns: list[str], wiktionary_url: str) -> None:
    title = f"*Word of the day*: *{word}*"

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": title}},
    ]

    # One section block per definition (plain_text). Always renders as separate lines.
    if defs:
        for d in defs:
            blocks.append({
                "type": "section",
                "text": {"type": "plain_text", "text": f"• {d}", "emoji": False}
            })
    else:
        blocks.append({
            "type": "section",
            "text": {"type": "plain_text", "text": "No definition found.", "emoji": False}
        })

    # Synonyms (optional block)
    if syns:
        blocks.append({
            "type": "section",
            "text": {"type": "plain_text", "text": "Synonyms: " + ", ".join(syns), "emoji": False}
        })

    # Footer / link
    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": f"<{wiktionary_url}|More on Wiktionary>"}]
    })

    # Fallback text for notifications (no links)
    fallback_lines = defs if defs else ["No definition found."]
    payload = {
        "text": f"Word of the day: {word}\n" + "\n".join(fallback_lines),
        "unfurl_links": False,
        "unfurl_media": False,
        "blocks": blocks
    }

    req = Request(
        SLACK_WEBHOOK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=12) as r:
        r.read()

# ---------- main ----------

def main() -> None:
    word = get_random_word()
    defs, syns = get_word_data(word)
    wiktionary = f"https://en.wiktionary.org/wiki/{quote(word)}"
    post_to_slack(word, defs, syns, wiktionary)

if __name__ == "__main__":
    main()
