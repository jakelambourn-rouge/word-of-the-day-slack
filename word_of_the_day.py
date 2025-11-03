#!/usr/bin/env python3
"""
Posts a word of the day to Slack via Incoming Webhook.

Sources:
- Random word: https://random-word-api.herokuapp.com/word (fallback: local list)
- Definitions: https://api.dictionaryapi.dev/api/v2/entries/en/<word>
If no definition found, link to Wiktionary.
"""

import json, os, random, re, textwrap
from urllib.request import urlopen, Request
from urllib.error import URLError
from urllib.parse import quote

SLACK_WEBHOOK_URL = os.environ["SLACK_WEBHOOK_URL"]

HEADERS = {"User-Agent": "wotd-bot/1.0"}

def fetch(url):
    try:
        with urlopen(Request(url, headers=HEADERS), timeout=10) as r:
            return r.read().decode("utf-8")
    except URLError:
        return None

def get_random_word():
    # Primary: random-word API
    data = fetch("https://random-word-api.herokuapp.com/word?number=1")
    if data:
        try:
            w = json.loads(data)[0]
            return w.strip()
        except Exception:
            pass
    # Fallback: local curated list
    fallback = ["serendipity","parsimonious","lachrymose","pellucid","obdurate",
                "ephemeral","ameliorate","cacophony","loquacious","incisive",
                "obviate","salubrious","winsome","evanescent","truculent"]
    return random.choice(fallback)

def tidy_definitions(entries):
    defs = []
    for e in entries:
        for m in e.get("meanings", []):
            pos = m.get("partOfSpeech", "")
            for d in m.get("definitions", []):
                defi = d.get("definition")
                if defi:
                    line = (f"{pos}: {defi}" if pos else defi).strip()
                    # compress whitespace
                    line = re.sub(r"\s+", " ", line)
                    defs.append(line)
    # de-dup and shorten
    seen, out = set(), []
    for d in defs:
        if d not in seen:
            seen.add(d)
            out.append(d[:240])  # keep Slack nice
        if len(out) >= 3:
            break
    return out

def get_definitions(word):
    data = fetch(f"https://api.dictionaryapi.dev/api/v2/entries/en/{quote(word)}")
    if not data:
        return []
    try:
        entries = json.loads(data)
        if isinstance(entries, list):
            return tidy_definitions(entries)
    except Exception:
        pass
    return []

def post_to_slack(text, blocks=None):
    payload = {"text": text}
    if blocks:
        payload["blocks"] = blocks
    req = Request(
        SLACK_WEBHOOK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=10) as r:
        r.read()

def main():
    word = get_random_word()
    defs = get_definitions(word)
    wiktionary = f"https://en.wiktionary.org/wiki/{quote(word)}"

    if defs:
        bullet = "\n".join(f"• {d}" for d in defs)
        text = f"*Word of the day*: *{word}*\n{bullet}"
        blocks = [
            {"type":"section","text":{"type":"mrkdwn","text":f"*Word of the day*: *{word}*"}},
            {"type":"section","text":{"type":"mrkdwn","text":bullet}},
            {"type":"context","elements":[{"type":"mrkdwn","text":f"<{wiktionary}|More on Wiktionary>"}]},
        ]
    else:
        text = f"*Word of the day*: *{word}*\nNo definition found. See {wiktionary}"
        blocks = [
            {"type":"section","text":{"type":"mrkdwn","text":f"*Word of the day*: *{word}*"}},
            {"type":"context","elements":[{"type":"mrkdwn","text":f"<{wiktionary}|Wiktionary>"}]},
        ]

    post_to_slack(text, blocks)

if __name__ == "__main__":
    main()
