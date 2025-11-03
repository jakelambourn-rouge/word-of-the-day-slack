#!/usr/bin/env python3
"""
Word of the Day to Slack via Incoming Webhook.

Primary: dictionaryapi.dev
Fallback: Wiktionary REST: /api/rest_v1/page/definition/<word>?redirect=true

Env:
- SLACK_WEBHOOK_URL
"""

import json
import os
import random
import re
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from urllib.parse import quote
from datetime import datetime
from zoneinfo import ZoneInfo  # built-in from Python 3.9+

def should_post_now(target_hour: int, target_minute: int) -> bool:
    now = datetime.now(ZoneInfo("Europe/London"))
    return now.hour == target_hour and now.minute == target_minute

SLACK_WEBHOOK_URL = os.environ["SLACK_WEBHOOK_URL"]
HEADERS = {"User-Agent": "wotd-bot/1.5 (contact: example@example.com)"}

# -------- helpers --------

def fetch(url: str) -> str | None:
    try:
        with urlopen(Request(url, headers=HEADERS), timeout=15) as r:
            return r.read().decode("utf-8")
    except (URLError, HTTPError):
        return None

TAG_RE = re.compile(r"<[^>]+>")
URL_RE = re.compile(r"https?://\S+")
WS_RE  = re.compile(r"\s+")

def clean_text(s: str) -> str:
    s = TAG_RE.sub("", s)
    s = URL_RE.sub("", s)
    s = WS_RE.sub(" ", s).strip()
    return s

def dedupe_keep_order(items, limit):
    seen, out = set(), []
    for x in items:
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x[:240])
        if len(out) >= limit:
            break
    return out

# -------- word source --------

def get_random_word() -> str:
    data = fetch("https://random-word-api.herokuapp.com/word?number=1")
    if data:
        try:
            w = json.loads(data)[0]
            return str(w).strip()
        except Exception:
            pass
    # Safe fallback list
    fallback = [
        "serendipity","parsimonious","pellucid","obdurate","ephemeral",
        "ameliorate","cacophony","loquacious","incisive","salubrious",
        "winsome","evanescent","truculent","cogent","sagacious",
    ]
    return random.choice(fallback)

# -------- dictionaryapi.dev --------

def parse_free_dict(entries: list) -> tuple[list[str], list[str]]:
    defs, syns = [], []
    for e in entries:
        for m in e.get("meanings", []):
            pos = m.get("partOfSpeech", "")
            for d in m.get("definitions", []):
                defi = clean_text(d.get("definition", ""))
                if defi:
                    defs.append(f"{pos}: {defi}" if pos else defi)
            for s in m.get("synonyms", []):
                s = clean_text(s)
                if s:
                    syns.append(s)
    return dedupe_keep_order(defs, 3), dedupe_keep_order(syns, 6)

def get_from_free_dict(word: str) -> tuple[list[str], list[str]]:
    data = fetch(f"https://api.dictionaryapi.dev/api/v2/entries/en/{quote(word)}")
    if not data:
        return [], []
    try:
        parsed = json.loads(data)
        if isinstance(parsed, list):
            return parse_free_dict(parsed)
    except Exception:
        pass
    return [], []

# -------- Wiktionary REST fallback --------
# Docs: https://en.wiktionary.org/api/rest_v1/ (definition endpoint)
# Shape: { "en": [ { "partOfSpeech": "...", "definitions": [ {"definition": "...", "synonyms": [...]} ] }, ... ] }

def get_from_wiktionary(word: str) -> tuple[list[str], list[str]]:
    url = f"https://en.wiktionary.org/api/rest_v1/page/definition/{quote(word)}?redirect=true"
    data = fetch(url)
    if not data:
        return [], []
    try:
        obj = json.loads(data)
    except Exception:
        return [], []

    entries = obj.get("en") or obj.get("en-gb") or []
    defs, syns = [], []

    for entry in entries:
        pos = entry.get("partOfSpeech", "")
        for d in entry.get("definitions", []):
            defi = clean_text(d.get("definition", ""))
            if defi:
                defs.append(f"{pos}: {defi}" if pos else defi)
            for s in d.get("synonyms", []) or []:
                s = clean_text(s)
                if s:
                    syns.append(s)

    return dedupe_keep_order(defs, 3), dedupe_keep_order(syns, 6)

# -------- Slack --------

def post_to_slack(word: str, defs: list[str], syns: list[str], wiktionary_url: str) -> None:
    title = f"*Word of the day*: *{word}*"
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": title}}]

    if defs:
        for d in defs:
            blocks.append({"type": "section",
                           "text": {"type": "plain_text", "text": f"• {d}", "emoji": False}})
    else:
        blocks.append({"type": "section",
                       "text": {"type": "plain_text", "text": "No definition found.", "emoji": False}})

    if syns:
        blocks.append({"type": "section",
                       "text": {"type": "plain_text", "text": "Synonyms: " + ", ".join(syns), "emoji": False}})

    blocks.append({"type": "context",
                   "elements": [{"type": "mrkdwn", "text": f"<{wiktionary_url}|More on Wiktionary>"}]})

    fallback = "Word of the day: " + word + "\n" + ("\n".join(defs) if defs else "No definition found.")
    payload = {
        "text": fallback,
        "unfurl_links": False,
        "unfurl_media": False,
        "blocks": blocks
    }

    req = Request(
        SLACK_WEBHOOK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=15) as r:
        r.read()

# -------- main --------

def main() -> None:
    target_hour = int(os.getenv("TARGET_HOUR_LONDON", "9"))
    target_minute = int(os.getenv("TARGET_MINUTE_LONDON", "0"))

    if not should_post_now(target_hour, target_minute):
        # Skip if it’s not the target time in London
        return

    word = get_random_word()
    defs, syns = get_from_free_dict(word)
    if not defs:
        defs, syns = get_from_wiktionary(word)
    wiktionary = f"https://en.wiktionary.org/wiki/{quote(word)}"
    post_to_slack(word, defs, syns, wiktionary)

if __name__ == "__main__":
    main()
