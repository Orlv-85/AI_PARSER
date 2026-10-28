"""Helpers for the period brief tests: a hand-made period payload, its digest items and a fake
provider behind `httpx.MockTransport` (no test makes a real call)."""
import hashlib
import json
from datetime import date, timedelta

import httpx

from app.core.periodic.period_model import period_bounds
from app.storage.digest_repo import NewsDigestRepo
from app.storage.period_signals import PeriodSignalRepo

PRO = "deepseek-v4-pro"
NAMES = ("Atlas", "Borealis", "Cygnus", "Draco", "Ember", "Falcon")
WEEK_START = date(2026, 10, 19)


def summary(name):
    return f"Acme launched the {name} model with open weights for everyone"


def story_url(name, start):
    return f"https://{name.lower()}.example.com/{start.isoformat()}/post"


def period_payload(kind="week", start=WEEK_START, *, status="ready", stories=5, quiet=False,
                   rising=False, items=300):
    """A stored period payload with `stories` top stories, each with one linked article."""
    end = period_bounds(kind, start)[1]
    top = [{"label": f"Acme launches {name}", "event_type": "model_release", "entities": [name],
            "days": [start.isoformat()], "articles": 2, "publishers": 2,
            "links": [{"url": story_url(name, start), "title": f"Acme launches {name} model",
                       "publisher": f"{name.lower()}.example.com"}]}
           for name in NAMES[:stories]]
    risers = [{"entity_id": 1, "name": "Zeta", "type": "model", "vendor": "Acme", "publishers": 2,
               "links": [{"url": story_url("Zeta", start), "title": "Acme launches Zeta model",
                          "publisher": "zeta.example.com"}]}] if rising else []
    return {"period_kind": kind, "period_start": start.isoformat(), "period_end": end.isoformat(),
            "status": status, "methodology_version": "m", "extraction_version": "e",
            "thresholds": {}, "coverage": {"items": items, "days": 7, "complete_days": 7},
            "quiet": quiet, "comparison": {"state": "ready"},
            "sections": {"rising": "ready" if rising else "hidden"},
            "top_stories": top, "top_entities": {}, "new": [], "rising": risers, "cooling": [],
            "event_mix": {"types": [{"event_type": "model_release", "label": "Model release",
                                     "stories": stories, "articles": 2 * stories}]}}


def store_digest(maker, payload):
    """For each linked article of the payload, a digest item on the second day of the period."""
    start = date.fromisoformat(payload["period_start"])
    items = [{"title": link["title"], "summary": summary(link["title"].split()[2]),
              "url": link["url"]}
             for group in ("top_stories", "rising") for item in payload[group]
             for link in item["links"]]
    with maker() as session:
        NewsDigestRepo(session).save_digest(
            report_date=start + timedelta(days=1), groups=[{"title": "Models", "items": items}])
        session.commit()


def store_period(maker, payload, *, digest=True):
    """The period row and, unless `digest` is false, the digest items of its articles."""
    with maker() as session:
        PeriodSignalRepo(session, comparable_from=date(2026, 10, 10)).save_report(
            payload, hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest())
        session.commit()
    if digest:
        store_digest(maker, payload)


def good_answer(request, *, sentences=4, model=PRO, usage=(3000, 400)):
    """A valid answer built from the packet in the request: one sentence per story."""
    body = json.loads(request.content)
    packet = json.loads(body["messages"][1]["content"])
    out = []
    for story in packet["stories"][:sentences]:
        article = story["articles"][0]
        text = packet["articles"][article]["summary"]
        out.append({"text": text + ".", "ids": [article],
                    "quote": {"id": article, "span": " ".join(text.split()[1:7])}})
    return answer({"sentences": out}, model=model, usage=usage)


def bad_answer(request):
    return good_answer(request, sentences=1)


def answer(content, *, model=PRO, usage=(3000, 400), finish="stop"):
    return httpx.Response(200, json={
        "model": model, "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]},
        "choices": [{"finish_reason": finish, "message": {"content": json.dumps(content)}}]})


class Provider:
    """Records each request body; answers with `handler(request)` (valid by default)."""

    def __init__(self, handler=good_answer):
        self.handler = handler
        self.requests = []

    def __call__(self, request):
        self.requests.append(json.loads(request.content))
        return self.handler(request)

    @property
    def transport(self):
        return httpx.MockTransport(self)
