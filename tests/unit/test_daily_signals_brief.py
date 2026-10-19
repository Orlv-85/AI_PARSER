import copy
import json
from pathlib import Path

import pytest

from app.core import daily_signals_brief as brief
from app.core.daily_signals_brief import (
    BRIEF_PROMPT,
    BRIEF_VERSION,
    BriefInvalid,
    PacketTooLarge,
    brief_packet,
    brief_payload,
    input_hash,
    is_review,
    parse_brief,
    request_body,
)
from app.storage.legacy_cleanup import encoded, fingerprint

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "daily_signals" / "brief"
PRO = "deepseek-v4-pro"
REVIEW_SENTENCE = " Stories with kind 'review' count as reviews."


def load(name):
    return json.loads((FIXTURES / name).read_text())


RESPONSES = load("responses.json")
ANSWERS = load("answers.json")
REV2 = load("report-rev2.json")
ONE_LINERS = load("one_liners.json")


def digest(day):
    return [item for group in load(f"dig-{day}.json")["groups"] for item in group["items"]]


def payload(day, *, spikes=False):
    """A stored snapshot built from the API answer, with the dry-run one-liners and folding."""
    data = load(f"sig-{day}.json")
    for item in data["new"]:
        item["one_liner"] = ONE_LINERS[f"{day}/{item['name']}"]["one_liner"]
    if not spikes:
        data["rising"] = []
    data["quiet"] = data["coverage"]["items"] < 20 or not data["top_stories"]
    return data


def answer(content, model=PRO, finish="stop"):
    return {"model": model, "choices": [{"finish_reason": finish, "message": {
        "content": content if isinstance(content, str) else json.dumps(content)}}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 100}}


def response_with(content_test):
    found = [v["data"] for v in RESPONSES.values()
             if content_test(v["data"]["choices"][0]["message"]["content"])]
    assert len(found) >= 1
    return found[0]


def brief2_body(packet, model=PRO):
    body = request_body(packet, model)
    body["messages"][0]["content"] = BRIEF_PROMPT.replace(
        "daily-signals-brief-3", "daily-signals-brief-2").replace(REVIEW_SENTENCE, "")
    return body


# Packet --------------------------------------------------------------------------------------
def test_packet_reproduces_the_dry_run_packet_with_review_marker():
    packet, id_map = brief_packet(payload("2026-10-16"), digest("2026-10-16"))
    expected = copy.deepcopy(REV2["2026-10-16"]["data"])
    expected["stories"][2]["kind"] = "review"  # Surface Laptop Ultra review story (O1)
    assert packet == expected
    assert id_map["a1"] == {"title": expected["articles"]["a1"]["title"],
                            "url": load("sig-2026-10-16.json")["top_stories"][0]["links"][0]["url"],
                            "publisher": "huggingface.co"}
    assert list(id_map) == [f"a{i}" for i in range(1, len(id_map) + 1)]


def test_packet_body_is_the_measured_brief_2_request():
    # The dry-run cached each answer under the sha256 of its request body: same packet, same
    # brief-2 prompt text, same request parameters.
    for day in ("2026-10-13", "2026-10-15", "2026-10-16"):
        packet = REV2[day]["data"]
        assert fingerprint(brief2_body(packet)) in RESPONSES


def test_quiet_packet_includes_the_digest():
    packet, _ = brief_packet(payload("2026-10-18"), digest("2026-10-18"))
    assert packet == ANSWERS["2026-10-18/deepseek-v4-pro"]["packet"]
    assert packet["quiet"] and len(packet["articles"]) == 14


def test_quiet_packet_takes_at_most_30_digest_items_and_digest_publisher():
    data = payload("2026-10-18")
    items = [{"title": f"Item {i}", "summary": "s", "url": f"https://x{i}.com/a",
              "publisher": f"x{i}.com"} for i in range(40)]
    packet, id_map = brief_packet(data, items)
    assert len(packet["articles"]) == 30
    assert packet["articles"]["a1"]["publisher"] == "x0.com"
    assert id_map["a30"]["url"] == "https://x29.com/a"


def test_packet_shrinks_summaries_to_the_byte_cap():
    data = payload("2026-10-18")
    items = [{"title": f"Item {i}", "summary": " ".join(["word"] * 200),
              "url": f"https://x{i}.com/a"} for i in range(30)]
    packet, _ = brief_packet(data, items)
    size = len(encoded(packet).encode())
    assert size <= brief.PACKET_MAX_BYTES
    lengths = {len(a["summary"]) for a in packet["articles"].values()}
    assert len(lengths) == 1 and 120 <= lengths.pop() < 600
    huge = [{"title": "T" * 500, "summary": "word " * 200, "url": f"https://x{i}.com/a"}
            for i in range(30)]
    with pytest.raises(PacketTooLarge):
        brief_packet(data, huge)


def test_review_marker_on_dry_run_days():
    marked = {}
    for day in ("2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16"):
        packet, _ = brief_packet(payload(day), digest(day))
        marked[day] = [s["label"] for s in packet["stories"] if s.get("kind") == "review"]
    assert marked["2026-10-12"] == marked["2026-10-13"] == marked["2026-10-14"] == []
    assert len(marked["2026-10-15"]) == 1 and "Gemini 4 Argon" in marked["2026-10-15"][0]
    assert marked["2026-10-16"] == ["Microsoft Surface Laptop Ultra Review: The First Real AI PC"]
    assert is_review(["A vs. B", "news"]) and not is_review(["news", "more news", "A review"])
    assert not is_review(["Off to a Good Start, But Performance Is Mixed"]) and not is_review([])


def test_packet_spikes_and_event_counts():
    packet, _ = brief_packet(payload("2026-10-16", spikes=True), digest("2026-10-16"))
    assert [s["name"] for s in packet["spikes"]][:2] == ["Hugging Face", "Beam"]
    assert set(packet["spikes"][0]) == {"name", "today", "usual_per_day", "articles"}
    assert "analysis" not in packet["event_counts"] and packet["event_counts"]["model releases"]


def test_input_hash_changes_with_packet_version_and_model(monkeypatch):
    packet = REV2["2026-10-16"]["data"]
    base = input_hash(packet, PRO)
    assert base == input_hash(copy.deepcopy(packet), PRO)
    assert input_hash(packet, "deepseek-flash") != base
    changed = copy.deepcopy(packet)
    changed["digest_items"] += 1
    assert input_hash(changed, PRO) != base
    monkeypatch.setattr(brief, "BRIEF_VERSION", "daily-signals-brief-4")
    assert input_hash(packet, PRO) != base


# Body ----------------------------------------------------------------------------------------
def test_body_and_prompt_pinned():
    packet = REV2["2026-10-16"]["data"]
    body = request_body(packet, PRO)
    assert body == {"model": PRO, "temperature": 0, "thinking": {"type": "disabled"},
                    "max_tokens": 900, "response_format": {"type": "json_object"},
                    "messages": [{"role": "system", "content": BRIEF_PROMPT},
                                 {"role": "user", "content": encoded(packet)}]}
    assert BRIEF_VERSION == "daily-signals-brief-3"
    assert BRIEF_PROMPT.startswith("Task: daily-signals-brief-3. ")
    assert "only when nothing else is left. Stories with kind 'review' count as reviews. At " \
        "most one sentence per story or item." in BRIEF_PROMPT
    assert BRIEF_PROMPT.isascii()
    recovery = request_body(packet, PRO, recovery="same_story (sentence 2)")
    assert recovery["messages"][0]["content"] == BRIEF_PROMPT + \
        " Correct the previous answer, rejected for: same_story (sentence 2)."


# Validation on the dry-run answers -----------------------------------------------------------
def test_brief_2_answers_pass():
    for day, run in REV2.items():
        packet = run["data"]
        data = RESPONSES[fingerprint(brief2_body(packet))]["data"]
        sentences = parse_brief(data, packet, PRO)
        assert [s.text for s in sentences] == [s["text"] for s in run["brief"]["sentences"]], day


def _accepted(key):
    sentences = ANSWERS[key]["sentences"]
    return response_with(lambda c: (json.loads(c) or {}).get("sentences") == sentences)


def test_revision_1_answers_ten_pass_four_fail_same_story():
    outcomes = {}
    for key, run in ANSWERS.items():
        model = key.split("/")[1]
        try:
            parse_brief(_accepted(key), run["packet"], model)
            outcomes[key] = "ok"
        except BriefInvalid as error:
            outcomes[key] = error.code
    assert len(outcomes) == 14
    assert sorted(outcomes.values()) == ["ok"] * 10 + ["same_story"] * 4


def test_rejected_first_attempts_fail_with_their_codes():
    rejected = {k: a for k, run in ANSWERS.items() for a in run["attempts"] if "raw" in a}
    assert {k: a["result"] for k, a in rejected.items()} == {
        "2026-10-14/deepseek-v4-pro": "sentence_count",
        "2026-10-15/deepseek-flash": "quote_not_found (sentence 2)",
        "2026-10-15/deepseek-v4-pro": "quote_schema (sentence 5)"}
    for key, attempt in rejected.items():
        data = response_with(lambda c, raw=attempt["raw"]: c == raw)
        with pytest.raises(BriefInvalid) as error:
            parse_brief(data, ANSWERS[key]["packet"], key.split("/")[1])
        assert str(error.value) == attempt["result"]


# Validation codes ----------------------------------------------------------------------------
PACKET = {
    "day": "2026-10-16", "quiet": False, "digest_items": 58,
    "stories": [{"label": "Reflection releases Beam", "outlets": 4, "event": "model_release",
                 "articles": ["a1", "a2"]}],
    "new": [{"name": "d1-ultra", "type": "model", "vendor": "Liquid AI", "outlets": 1,
             "what": "Today, we release d1-ultra, our new multimodal decision model",
             "articles": ["a3"]}],
    "spikes": [], "event_counts": {"model releases": 2},
    "articles": {
        "a1": {"title": "Welcome Beam: a 501B open model", "publisher": "huggingface.co",
               "summary": "Reflection AI released Beam, an open model with day-0 support."},
        "a2": {"title": "Reflection's Beam aims to undercut rivals", "publisher": "venturebeat.com",
               "summary": "Beam was trained with heavy reinforcement learning."},
        "a3": {"title": "d1-ultra: Introducing a decision model", "publisher": "liquid.ai",
               "summary": "Liquid AI says d1-ultra outperforms rivals at the same price."},
        "a4": {"title": "Acme raises money for chips", "publisher": "techcrunch.com",
               "summary": "Acme Robotics raised a new round led by Example Ventures."}}}
S1 = {"text": "Reflection AI released Beam, a 501B open model, covered by 4 outlets.",
      "ids": ["a1", "a2"], "quote": {"id": "a1", "span": "Reflection AI released Beam, an open"}}
S2 = {"text": "Liquid AI says d1-ultra outperforms rivals at the same price.", "ids": ["a3"],
      "quote": {"id": "a3", "span": "Today, we release d1-ultra, our new"}}
S3 = {"text": "Acme Robotics raised a new round, according to TechCrunch.", "ids": ["a4"],
      "quote": {"id": "a4", "span": "Acme Robotics raised a new round"}}


def check(sentences, packet=None, **answer_options):
    packet = PACKET if packet is None else packet
    return parse_brief(answer({"sentences": sentences}, **answer_options), packet, PRO)


def with_(sentence, **changes):
    return {**copy.deepcopy(sentence), **changes}


def test_minimal_valid_answer_and_stored_payload():
    sentences = check([S1, S2, S3])
    assert [s.ids for s in sentences] == [("a1", "a2"), ("a3",), ("a4",)]
    id_map = {k: {"title": v["title"], "url": f"https://{v['publisher']}/x",
                         "publisher": v["publisher"]} for k, v in PACKET["articles"].items()}
    stored = brief_payload(sentences, id_map)
    assert stored["sentences"][0] == {"text": S1["text"], "quote": S1["quote"]["span"],
                                      "links": [id_map["a1"], id_map["a2"]]}


@pytest.mark.parametrize(("data", "code"), [
    (answer({"sentences": [S1, S2, S3]}, model="deepseek-flash"), "model"),
    (answer({"sentences": [S1, S2, S3]}, finish="length"), "truncated"),
    (answer("not json"), "schema"),
    (answer({"sentences": [S1, S2, S3], "extra": 1}), "schema"),
    (answer({"sentences": "x"}), "schema"),
    ({"model": PRO, "choices": []}, "schema"),
    (answer({"sentences": [S1, S2]}), "sentence_count"),
    (answer({"sentences": [S1, S2, S3, S3, S3, S3]}), "sentence_count"),
])
def test_answer_level_codes(data, code):
    with pytest.raises(BriefInvalid) as error:
        parse_brief(data, PACKET, PRO)
    assert error.value.code == code and error.value.sentence is None


@pytest.mark.parametrize(("bad", "code"), [
    ("not a dict", "schema"),
    (with_(S3, extra=1), "schema"),
    (with_(S3, text="Too short."), "text_length"),
    (with_(S3, text="Acme Robotics raised a new round. " * 8), "text_length"),
    (with_(S3, text="Acme Robotics raised a new round, see https://techcrunch.com."),
     "url_or_markup"),
    (with_(S3, text="Acme Robotics raised a **new** round, according to TechCrunch."),
     "url_or_markup"),
    (with_(S3, text="Acme Robotics raised a new round #funding, according to TechCrunch."),
     "url_or_markup"),
    (with_(S3, text="Acme Robotics raised a new round, по TechCrunch."), "non_english"),
    (with_(S3, ids=["a9"]), "unknown_id"),
    (with_(S3, ids=[]), "unknown_id"),
    (with_(S3, ids=["a1", "a2", "a3", "a4"]), "unknown_id"),
    (with_(S3, quote={"id": "a1", "span": "Acme Robotics raised a new round"}), "quote_schema"),
    (with_(S3, quote={"id": "a4", "span": "Acme Robotics raised"}), "quote_schema"),
    (with_(S3, quote={"id": "a4", "span": "word " * 41}), "quote_schema"),
    (with_(S3, quote={"id": "a4", "span": "Acme Robotics raised a huge round"}),
     "quote_not_found"),
    (with_(S3, text="Acme Robotics raised 40 million dollars, according to TechCrunch."),
     "unsupported_number"),
    (with_(S3, text="Acme Robotics raised a new round led by Sequoia, says TechCrunch."),
     "unsupported_name"),
    (with_(S3, ids=["a3"], quote={"id": "a3", "span": "Liquid AI says d1-ultra outperforms"},
           text="Liquid AI says d1-ultra outperforms rivals at the same price again."),
     "duplicate_sentence"),
    (with_(S3, ids=["a2"], text="Beam was trained with heavy reinforcement learning, it says.",
           quote={"id": "a2", "span": "Beam was trained with heavy reinforcement"}),
     "same_story"),
])
def test_sentence_codes(bad, code):
    with pytest.raises(BriefInvalid) as error:
        check([S1, S2, bad])
    assert (error.value.code, error.value.sentence) == (code, 3)
    assert str(error.value) == f"{code} (sentence 3)"


def test_grounding_allowances():
    # Typographic quotes and case are folded; numbers may be outlet counts or (quiet) the item
    # count; names may come from item names, vendors and publisher domain stems.
    curly = with_(S2, quote={"id": "a3", "span": "today, we release d1‑ultra, our new"})
    check([S1, curly, S3])
    quiet = {**PACKET, "quiet": True, "digest_items": 14}
    check([with_(S3, text="Quiet day with 14 items: Acme Robotics raised, TechCrunch says.")],
          packet=quiet)
    with pytest.raises(BriefInvalid, match="unsupported_number"):
        check([S1, S2, with_(S3, text="Acme Robotics raised a round, covered by 4 outlets.")])
