import ast
import importlib.util
import json
import shutil
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml


def _load_bridge_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "digest_generator.py"
    spec = importlib.util.spec_from_file_location("deepseek_digest_bridge", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generator_supports_server_host_python() -> None:
    source = Path("scripts/digest_generator.py").read_text(encoding="utf-8")
    ast.parse(source, feature_version=(3, 10))


def test_generator_exposes_only_current_provider_and_prompt() -> None:
    generator = _load_bridge_module()
    parser = generator.__dict__["_build_parser"]()
    assert "publish-antigravity-digest" not in parser.format_help()
    args = parser.parse_args(
        [
            "publish-deepseek-digest",
            "--base-url",
            "http://example.test",
            "--report-date",
            "2026-10-03",
        ]
    )
    assert Path(args.prompt).is_file()
    assert Path(args.prompt).name == "digest_prompt.txt"


def test_compose_contains_only_application_services() -> None:
    config = yaml.safe_load(Path("docker-compose.prod.yml").read_text(encoding="utf-8"))
    assert set(config["services"]) == {"app", "db", "caddy"}


def test_deepseek_retries_network_timeout(monkeypatch) -> None:
    generator = _load_bridge_module()
    items = [{"url": "https://example.com/story", "summary": "A concrete finding."}]
    responses = iter(
        [
            RuntimeError("Network timeout for https://api.deepseek.com/chat/completions"),
            _completion(items),
        ]
    )

    def read(*_args, **_kwargs):
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(generator, "read_json_response", read)
    result = generator.run_deepseek_chunk(
        api_key="test-only-key",
        model="deepseek-flash",
        prompt="Return JSON.",
        report_date="2026-10-03",
        articles=[{"url": items[0]["url"], "title": "Finding"}],
    )
    assert result == {items[0]["url"]: items[0]["summary"]}


@pytest.mark.parametrize("field", ["summary", "content"])
def test_fallback_uses_clean_article_text(field) -> None:
    bridge = _load_bridge_module()
    payload = bridge.build_feed_digest_payload(
        items=[
            {
                "title": "A new release",
                "url": "https://example.com/story",
                "summary": "No summary available.",
                field: (
                    "<style>secret CSS</style><script>alert(1)</script><template>hidden</template>"
                    "<p>The release adds <b>retrieval</b> with reranking &amp; citations.</p>"
                    "<p>The post A new release appeared first on Example.</p>"
                ),
            }
        ],
        report_date="2026-10-03",
    )
    summary = payload["groups"][0]["items"][0]["summary"]
    assert summary == "The release adds retrieval with reranking & citations."
    assert "Source:" not in summary


def test_fallback_bounds_long_excerpt_and_ignores_placeholder_summary() -> None:
    bridge = _load_bridge_module()
    excerpt = bridge.__dict__["_source_excerpt"](
        {
            "summary": "Source: Example. Included in the daily digest.",
            "content": "A concrete result. " + "Another useful result " * 50,
        }
    )
    assert excerpt == "A concrete result."
    assert len(excerpt) <= 400
    excerpt = bridge.__dict__["_source_excerpt"]({"content": "specific detail " * 100})
    assert len(excerpt) <= 400
    assert excerpt.endswith("...")


def _completion(items):
    return {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "content": json.dumps(
                        {
                            "report_date": "2026-10-03",
                            "items": items,
                        }
                    )
                },
            }
        ]
    }


def test_deepseek_sends_text_and_verifies_complete_coverage(monkeypatch) -> None:
    bridge = _load_bridge_module()
    captured = []
    result_items = [{"url": "https://example.com/story", "summary": "Release adds citations."}]

    def read(url, **kwargs):
        captured.append((url, kwargs))
        return _completion(result_items)

    monkeypatch.setattr(bridge, "read_json_response", read)
    result = bridge.run_deepseek_chunk(
        api_key="test-only-key",
        model="deepseek-flash",
        prompt="Return JSON summaries.",
        report_date="2026-10-03",
        articles=[
            {
                "url": "https://example.com/story",
                "title": "Release",
                "summary": "<p>A stored summary.</p>",
                "content": "<p>Full article details.</p>",
            }
        ],
    )
    assert result == {"https://example.com/story": "Release adds citations."}
    assert captured[0][0] == "https://api.deepseek.com/chat/completions"
    request = json.loads(captured[0][1]["body"])
    assert request["response_format"] == {"type": "json_object"}
    assert request["thinking"] == {"type": "disabled"}
    row = json.loads(request["messages"][1]["content"])["articles"][0]
    assert row["content"] == "Full article details."
    assert row["summary"] == "A stored summary."
    assert captured[0][1]["headers"] == {"Authorization": "Bearer test-only-key"}


@pytest.mark.parametrize(
    "bad_items",
    [
        [],
        [{"url": "https://example.com/other", "summary": "Wrong URL."}],
        [
            {
                "url": "https://example.com/story",
                "summary": "Source: X. Included in the daily digest.",
            }
        ],
        [{"url": "https://example.com/story", "summary": "x" * 401}],
        [{"url": "https://example.com/story", "summary": "Duplicate."}] * 2,
    ],
)
def test_deepseek_rejects_bad_response_without_publishing(monkeypatch, bad_items) -> None:
    bridge = _load_bridge_module()
    calls = []

    def read(url, **_kwargs):
        calls.append(url)
        if "/api/news/links" in url:
            assert "include_content=true" in url
            return [{"url": "https://example.com/story", "title": "Release", "content": "Details"}]
        assert url == "https://api.deepseek.com/chat/completions"
        return _completion(bad_items)

    monkeypatch.setattr(bridge, "read_json_response", read)
    with pytest.raises(RuntimeError, match="invalid summaries"):
        bridge.publish_deepseek_digest(
            base_url="http://example.test",
            report_date="2026-10-03",
            limit=200,
            api_key="test-only-key",
            model="deepseek-flash",
            prompt_path=Path("automation/digest_prompt.txt"),
        )
    assert len(calls) == 3
    assert not any("/api/news/digests" in url for url in calls)


def test_deepseek_request_errors_do_not_expose_key(monkeypatch) -> None:
    bridge = _load_bridge_module()

    def read(*_args, **_kwargs):
        raise RuntimeError("HTTP 401: test-only-key invalid")

    monkeypatch.setattr(bridge, "read_json_response", read)
    with pytest.raises(RuntimeError) as error:
        bridge.run_deepseek_chunk(
            api_key="test-only-key",
            model="deepseek-flash",
            prompt="Return JSON.",
            report_date="2026-10-03",
            articles=[],
        )
    assert "test-only-key" not in str(error.value)
    assert "[redacted]" in str(error.value)


def test_deepseek_publishes_all_chunks_and_verifies_saved_digest(monkeypatch) -> None:
    bridge = _load_bridge_module()
    saved = {}
    items = [
        {
            "title": "Release details",
            "url": f"https://example.com/{index}",
            "content": f"Release {index} adds citations.",
        }
        for index in range(2)
    ]
    ai_calls = []

    def read(url, **kwargs):
        if "/api/news/links" in url:
            return items
        if url == "https://api.deepseek.com/chat/completions":
            rows = json.loads(json.loads(kwargs["body"])["messages"][1]["content"])["articles"]
            ai_calls.append(rows)
            return _completion([{"url": row["url"], "summary": row["content"]} for row in rows])
        if "body" in kwargs:
            saved.update(json.loads(kwargs["body"]))
        return dict(saved)

    monkeypatch.setattr(bridge, "read_json_response", read)
    result = bridge.publish_deepseek_digest(
        base_url="http://example.test",
        report_date="2026-10-03",
        limit=200,
        api_key="test-only-key",
        model="deepseek-flash",
        chunk_size=1,
        prompt_path=Path("automation/digest_prompt.txt"),
    )
    assert result["mode"] == "deepseek"
    assert result["chunk_count"] == 2
    assert result["fetched_count"] == result["saved_count"] == 2
    assert len(ai_calls) == 2
    summaries = [row["summary"] for group in saved["groups"] for row in group["items"]]
    assert summaries == ["Release 0 adds citations.", "Release 1 adds citations."]


@pytest.mark.parametrize(
    "bad_response",
    [
        {"choices": []},
        {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]},
        {"choices": [{"finish_reason": "stop", "message": {"content": "not JSON"}}]},
    ],
)
def test_deepseek_retries_invalid_output(monkeypatch, bad_response) -> None:
    bridge = _load_bridge_module()
    good = [{"url": "https://example.com/story", "summary": "A concrete finding."}]
    responses = iter([bad_response, _completion(good)])
    monkeypatch.setattr(bridge, "read_json_response", lambda *_args, **_kwargs: next(responses))
    result = bridge.run_deepseek_chunk(
        api_key="test-only-key",
        model="deepseek-flash",
        prompt="Return JSON.",
        report_date="2026-10-03",
        articles=[{"url": good[0]["url"], "title": "Finding"}],
    )
    assert result == {good[0]["url"]: good[0]["summary"]}


def test_missing_key_fails_before_fetch_or_publish(monkeypatch) -> None:
    bridge = _load_bridge_module()
    monkeypatch.setattr(
        bridge, "read_json_response", lambda *_args, **_kwargs: pytest.fail("network")
    )
    with pytest.raises(RuntimeError, match="DS_API_KEY"):
        bridge.publish_deepseek_digest(
            base_url="http://example.test",
            report_date="2026-10-03",
            limit=200,
            api_key="",
            model="deepseek-flash",
            prompt_path=Path("unused"),
        )


def _daily_job(tmp_path, *, publish_exit=0, signals_exit=0, with_timeout=True, env=None,
               args=("2026-10-03",), from_scripts_dir=False):
    """Run the job script with fake docker/flock/timeout and only the tools it needs on PATH."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "run_daily_digest_job.sh"
    script.write_text(
        Path("scripts/run_daily_digest_job.sh").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tmp_path / ".env").write_text('DS_API_KEY="test-only-key"\n', encoding="utf-8")
    (tmp_path / ".last_deploy_image").write_text("release:tested\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("sh", "date", "cat", "dirname", "basename"):
        (bin_dir / tool).symlink_to(shutil.which(tool))
    fakes = {
        "docker": ('printf "docker %s|image=%s\\n" "$*" "$APP_IMAGE" >> "$TEST_LOG"\n'
                   'case "$*" in *daily-publish*) exit "$PUBLISH_EXIT";; '
                   '*daily-signals*) exit "$SIGNALS_EXIT";; esac\nexit 0\n'),
        "flock": 'printf "flock %s\\n" "$*" >> "$TEST_LOG"\nshift 3\nexec "$@"\n',
    }
    if with_timeout:
        fakes["timeout"] = 'printf "timeout %s\\n" "$*" >> "$TEST_LOG"\nshift 3\nexec "$@"\n'
    for name, body in fakes.items():
        (bin_dir / name).write_text("#!/bin/sh\n" + body, encoding="utf-8")
        (bin_dir / name).chmod(0o755)
    values = {
        "PATH": str(bin_dir), "HOME": str(tmp_path),
        "TEST_LOG": str(tmp_path / "calls"),
        "PUBLISH_EXIT": str(publish_exit), "SIGNALS_EXIT": str(signals_exit),
        "DS_API_KEY": "",
        **(env or {}),
    }
    command = ["sh", "./run_daily_digest_job.sh"] if from_scripts_dir else ["sh", str(script)]
    result = subprocess.run(
        [*command, *args], env=values, capture_output=True, text=True, check=False,
        cwd=scripts if from_scripts_dir else tmp_path,
    )
    log = tmp_path / "calls"
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return result, calls


@pytest.mark.parametrize("fallback", ["0", "1"])
def test_daily_job_publishes_then_runs_signals_under_one_lock(tmp_path, fallback) -> None:
    result, calls = _daily_job(tmp_path, env={"AINEWS_DIGEST_ALLOW_FALLBACK": fallback})
    assert result.returncode == 0, result.stderr
    flocks = [c for c in calls if c.startswith("flock ")]
    assert len(flocks) == 1 and "-w 7200 /tmp/ai-news-auto-update.lock" in flocks[0]
    docker = [c for c in calls if c.startswith("docker ")]
    assert len(docker) == 2
    assert "ai-news daily-publish --report-date 2026-10-03" in docker[0]
    assert all(c.endswith("image=release:tested") for c in docker)
    assert "--name ai-news-signals-2026-10-03 app ai-news daily-signals" in docker[1]
    assert "--report-date 2026-10-03 --max-seconds 2520" in docker[1]
    assert [c for c in calls if c.startswith("timeout ")] == [
        "timeout -k 30 2700 docker compose -f docker-compose.prod.yml run --rm --name "
        "ai-news-signals-2026-10-03 app ai-news daily-signals --report-date 2026-10-03 "
        "--max-seconds 2520"]
    assert "antigravity" not in " ".join(calls)
    assert "test-only-key" not in " ".join(calls) + result.stdout + result.stderr


def test_daily_job_publish_failure_skips_signals(tmp_path) -> None:
    result, calls = _daily_job(tmp_path, publish_exit=1)
    assert result.returncode == 1
    docker = [c for c in calls if c.startswith("docker ")]
    assert len(docker) == 1 and "daily-publish" in docker[0]


def test_daily_job_signals_failure_keeps_success_and_removes_container(tmp_path) -> None:
    result, calls = _daily_job(tmp_path, signals_exit=124)
    assert result.returncode == 0
    assert "daily-signals failed or timed out" in result.stderr
    assert calls[-1].startswith("docker rm -f ai-news-signals-2026-10-03")


def test_daily_job_skips_signals_when_budget_is_spent(tmp_path) -> None:
    started = str(int(time.time()) - 14000)
    result, calls = _daily_job(tmp_path, args=(), env={
        "AINEWS_DAILY_JOB_LOCKED": "1", "REPORT_DATE": "2026-10-03",
        "AINEWS_DAILY_JOB_START": started})
    assert result.returncode == 0
    assert "daily-signals skipped" in result.stderr
    assert [c for c in calls if c.startswith("flock ")] == []
    docker = [c for c in calls if c.startswith("docker ")]
    assert len(docker) == 1 and "--report-date 2026-10-03" in docker[0]


def test_daily_job_without_timeout_binary_runs_signals_directly(tmp_path) -> None:
    result, calls = _daily_job(tmp_path, with_timeout=False)
    assert result.returncode == 0, result.stderr
    assert not any(c.startswith("timeout ") for c in calls)
    assert "ai-news daily-signals" in [c for c in calls if c.startswith("docker ")][1]


def test_daily_job_locked_entry_without_start_or_date_falls_back(tmp_path) -> None:
    result, calls = _daily_job(tmp_path, args=(), env={"AINEWS_DAILY_JOB_LOCKED": "1"})
    assert result.returncode == 0, result.stderr
    yesterday = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    assert f"daily-publish --report-date {yesterday}" in calls[0]


def test_daily_job_started_by_relative_path(tmp_path) -> None:
    result, calls = _daily_job(tmp_path, from_scripts_dir=True)
    assert result.returncode == 0, result.stderr
    assert len([c for c in calls if c.startswith("docker ")]) == 2
