# pylint: disable=protected-access
import json

import httpx
import pytest

from app.config.settings import Settings
from app.core.sources import review as source_review
from app.core.sources.review import SourceProbe, SourceReviewer, evidence_fingerprint, probe_source

RSS = b'''<?xml version="1.0"?><rss version="2.0"><channel><title>AI News</title>
<description>AI research</description><item><title>New AI model</title>
<link>https://publisher.example/model</link><pubDate>Fri, 09 Oct 2026 12:00:00 GMT</pubDate>
</item></channel></rss>'''
HTML = b'''<html><head><title>AI Blog</title><meta name="description" content="Agents"/></head>
<body><nav><a href="/login">Login</a></nav>
<article><h2><a href="/post/1">Agent release</a></h2><time datetime="2026-10-09"/></article>
<article><h3><a href="/post/2">AI testing</a></h3></article></body></html>'''


def _settings(**kwargs) -> Settings:
    return Settings(_env_file=None, jev_enabled=True, jev_api_key="jev-test-key",
                    ds_api_key="ds-test-key", **kwargs)


def _jev_answers(**values) -> dict:
    return {"answers": {key: {"noul": values.get(key, 0.99)} for key in (
        "publication_source", "ai_coverage", "sufficient_evidence"
    )}}


@pytest.mark.parametrize("content,kind,count", [(RSS, "rss", 1), (HTML, "html", 2)])
def test_probe_uses_only_source_listing_and_records_bounded_evidence(
    monkeypatch, content, kind, count
) -> None:
    monkeypatch.setattr(source_review, "_ensure_public_url", lambda _url: None)
    calls = []

    def respond(request):
        calls.append(str(request.url))
        return httpx.Response(200, content=content)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        probe = probe_source(client, "https://publisher.example/feed")
    assert probe.source_type == kind
    assert probe.item_count == count
    assert calls == ["https://publisher.example/feed"]
    assert all(sample["title"] for sample in probe.samples)
    assert "Login" not in probe.brief("not JSON")
    if kind == "html":
        assert probe.samples[0]["date"] == "2026-10-09"


@pytest.mark.parametrize("content", [
    b"<rss version='2.0'><channel/></rss>",
    b"<html><a href='/login'>Login</a></html>",
    b"<html><h2><a href='/only-article'>Article</a></h2></html>",
    b"<rss version='2.0'><channel><item><title>Missing link</title></item></channel></rss>",
])
def test_probe_rejects_pages_without_publication_evidence(monkeypatch, content) -> None:
    monkeypatch.setattr(source_review, "_ensure_public_url", lambda _url: None)
    with httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(
        200, content=content
    ))) as client, pytest.raises(ValueError):
        probe_source(client, "https://publisher.example/feed")


@pytest.mark.parametrize("scenario", [
    "redirect", "redirect_loop", "missing_location", "oversize", "404",
])
def test_probe_bounds_redirects_and_body_size(monkeypatch, scenario) -> None:
    checked: list[str] = []
    monkeypatch.setattr(source_review, "_ensure_public_url", checked.append)

    def respond(request):
        if scenario == "oversize":
            return httpx.Response(200, content=b"x" * 1_000_001)
        if scenario == "404":
            return httpx.Response(404)
        if scenario == "missing_location":
            return httpx.Response(302)
        if request.url.path == "/feed" and scenario == "redirect":
            return httpx.Response(200, content=RSS)
        return httpx.Response(302, headers={"Location": "/feed"})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        if scenario == "redirect":
            assert probe_source(client, "https://publisher.example/start").source_type == "rss"
            assert len(checked) == 2
        else:
            with pytest.raises((ValueError, httpx.HTTPStatusError)):
                probe_source(client, "https://publisher.example/start")
    assert len(checked) <= 4


@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.0.0.1", "192.168.1.1", "169.254.169.254", "::1",
])
def test_private_network_sources_are_blocked(monkeypatch, address) -> None:
    monkeypatch.setattr(source_review.socket, "getaddrinfo", lambda *_a, **_k: [
        (None, None, None, None, (address, 443))
    ])
    with pytest.raises(ValueError, match="Private"):
        source_review._ensure_public_url("https://publisher.example/feed")


@pytest.mark.parametrize("url", ["file:///etc/passwd", "https://user:password@publisher.example"])
def test_non_http_and_credential_urls_are_blocked(url) -> None:
    with pytest.raises(ValueError, match="public"):
        source_review._ensure_public_url(url)


def test_public_resolution_and_empty_dns(monkeypatch) -> None:
    monkeypatch.setattr(source_review.socket, "getaddrinfo", lambda *_a, **_k: [
        (None, None, None, None, ("8.8.8.8", 443))
    ])
    source_review._ensure_public_url("https://publisher.example")
    monkeypatch.setattr(source_review.socket, "getaddrinfo", lambda *_a, **_k: [])
    with pytest.raises(ValueError):
        source_review._ensure_public_url("http://publisher.example")


def test_evidence_brief_ignores_full_articles_and_cache_depends_on_models() -> None:
    probe = SourceProbe("https://publisher.example/feed", "rss", "AI News", "Models",
                        [{"title": "Release", "url": "/post", "date": "2026-10-09"}], 1)
    brief = probe.brief(json.dumps({"name": "AI Source", "content": "secret full article"}))
    assert "secret" not in brief
    assert json.loads(brief)["declared_unverified"]["name"] == "AI Source"
    assert evidence_fingerprint(brief, _settings()) != evidence_fingerprint(
        brief, _settings(source_review_deepseek_model="different")
    )


@pytest.mark.parametrize("score,decision", [(0.99, "ready"), (0.01, "reject")])
def test_confident_jev_decision_does_not_call_deepseek(score, decision) -> None:
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=_jev_answers(ai_coverage=score))

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = SourceReviewer(_settings(), client).review("x" * 10000)
    assert result["decision"] == decision
    assert len(calls) == 1
    payload = json.loads(calls[0].content)
    assert len(payload["state"]) == 6000
    assert len(payload["questions"]) == 3
    assert calls[0].headers["Authorization"] == "Bearer jev-test-key"


@pytest.mark.parametrize("confidence,decision", [(0.99, "ready"), (0.7, "review")])
def test_uncertain_jev_routes_same_brief_to_deepseek(confidence, decision) -> None:
    calls = []

    def respond(request):
        calls.append(request)
        if "typesafe" in str(request.url):
            return httpx.Response(200, json=_jev_answers(ai_coverage=0.6))
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps({"decision": "ready", "confidence": confidence,
                                   "reason": "AI publication samples"})
        }}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = SourceReviewer(_settings(), client).review("bounded evidence")
    assert result["decision"] == decision
    assert result["provider"] == "deepseek"
    assert len(calls) == 2
    jev, deepseek = [json.loads(request.content) for request in calls]
    assert jev["state"] == deepseek["messages"][1]["content"]
    assert deepseek["max_tokens"] == 400
    assert deepseek["thinking"]["type"] == "disabled"


@pytest.mark.parametrize("failure", [
    "http", "invalid", "incomplete", "confidence", "decision", "reason",
])
def test_provider_failure_remains_manual_and_stops_repeated_provider_calls(failure) -> None:
    calls = []

    def respond(request):
        calls.append(str(request.url))
        if "typesafe" in str(request.url):
            return httpx.Response(200, json=_jev_answers(ai_coverage=0.6))
        if failure == "http":
            return httpx.Response(429, text="ds-test-key")
        result = {"decision": "ready", "confidence": 0.99, "reason": "Samples"}
        if failure == "confidence":
            result["confidence"] = True
        if failure == "decision":
            result["decision"] = "invented"
        if failure == "reason":
            result["reason"] = ""
        return httpx.Response(200, json={"choices": [{
            "finish_reason": "length" if failure == "incomplete" else "stop",
            "message": {"content": "oops" if failure == "invalid" else json.dumps(result)},
        }]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        reviewer = SourceReviewer(_settings(), client)
        assert reviewer.review("first")["decision"] == "review"
        second = reviewer.review("second")
    assert second["decision"] == "review"
    assert "ds-test-key" not in json.dumps(second)
    assert sum("deepseek" in url for url in calls) == 1


def test_missing_keys_jev_failure_and_deepseek_budget_never_approve() -> None:
    settings = Settings(_env_file=None, jev_enabled=True)
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(500, text="provider secret")

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        reviewer = SourceReviewer(settings, client)
        assert reviewer.review("no keys")["decision"] == "review"
        assert not calls
        reviewer = SourceReviewer(_settings(), client)
        reviewer.deepseek_calls = 50
        assert reviewer.review("first")["decision"] == "review"
        assert reviewer.review("second")["decision"] == "review"
    assert len(calls) == 1
