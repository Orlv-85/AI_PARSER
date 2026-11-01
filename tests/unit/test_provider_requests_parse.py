"""Branch tests for parsing paid Jev and DeepSeek responses (synthetic data only)."""
import json

import pytest

from app.core.daily.provider_requests import parse_jev, parse_summary
from app.storage.journal_files import fingerprint

ROW = {"url": "https://example.com/article/ai", "title": "Synthetic AI release",
       "content": "The AI system handles document extraction for hospitals.",
       "summary": "An old model summary must never reach the providers."}


def jev_response(**overrides):
    return {"model": "jev-1.13.0", "usage": {"input_tokens": 1000}, "answers": {
        "ai_relevant": {"noul": 0.99},
        "admission": {"choice": "accepted_ai_editorial", "confidence": 0.99},
        "category": {"choice": "AI Applications", "confidence": 0.9},
        "comparison": {"choice": "NotComparison", "confidence": 0.9},
    }, **overrides}


def test_jev_parse_rejects_unexpected_model_choice_and_probability():
    with pytest.raises(ValueError, match="Unexpected JEV model"):
        parse_jev(ROW, jev_response(model="other"))
    data = jev_response()
    data["answers"]["admission"]["choice"] = "not_a_choice"
    with pytest.raises(ValueError, match="Unknown choice"):
        parse_jev(ROW, data)
    data = jev_response()
    data["answers"]["ai_relevant"]["noul"] = 1.5
    with pytest.raises(ValueError, match="Invalid Jev probability"):
        parse_jev(ROW, data)
    data = jev_response()
    del data["answers"]["comparison"]
    with pytest.raises(KeyError):
        parse_jev(ROW, data)


def test_jev_parse_topic_and_comparison_thresholds():
    result = parse_jev(ROW, jev_response())
    assert result["topic"] == "AI Applications" and result["material_type"] is None
    assert not result["boundary_review"]
    data = jev_response()
    data["answers"]["comparison"] = {"choice": "Comparison", "confidence": 0.7}
    result = parse_jev(ROW, data)
    assert result["material_type"] == "Comparison" and not result["boundary_review"]
    data["answers"]["comparison"]["confidence"] = 0.69
    result = parse_jev(ROW, data)
    assert result["material_type"] is None and result["boundary_review"]
    data["answers"]["comparison"] = {"choice": "Unknown", "confidence": 0.99}
    assert parse_jev(ROW, data)["boundary_review"]
    data = jev_response()
    data["answers"]["category"] = {"choice": "Other", "confidence": 0.99}
    result = parse_jev(ROW, data)
    assert result["topic"] is None and result["boundary_review"]
    assert result["topic_raw"] == {"choice": "Other", "confidence": 0.99}
    data = jev_response()
    data["answers"]["admission"] = {"choice": "non_ai", "confidence": 0.99}
    data["answers"]["comparison"] = {"choice": "Comparison", "confidence": 0.99}
    result = parse_jev(ROW, data)
    assert result["topic"] is None and result["material_type"] is None
    assert not result["boundary_review"]


def summary_data(value, **choice):
    return {"model": "deepseek-flash", "choices": [{
        "finish_reason": "stop", "message": {"content": json.dumps(value)}, **choice}]}


def fact(sentence="The system extracts documents.", quote=ROW["content"]):
    return {"sentence": sentence, "quote": quote}


def test_summary_parse_rejects_bad_envelope():
    good = {"facts": [fact()], "compared_products": []}
    assert parse_summary(ROW, {**summary_data(good), "model": "deepseek-v4.1-flash"},
                         False)["model"] == "deepseek-v4.1-flash"
    with pytest.raises(ValueError, match="Unexpected DeepSeek model"):
        parse_summary(ROW, {**summary_data(good), "model": "other"}, False)
    with pytest.raises(ValueError, match="Incomplete summary"):
        parse_summary(ROW, summary_data(good, finish_reason="length"), False)
    with pytest.raises(json.JSONDecodeError):
        parse_summary(ROW, {"model": "deepseek-flash", "choices": [{
            "finish_reason": "stop", "message": {"content": "not json"}}]}, False)
    with pytest.raises(KeyError):
        parse_summary(ROW, summary_data({"facts": [fact()]}), False)


@pytest.mark.parametrize("facts", [[], [fact()] * 4, "text", None])
def test_summary_parse_requires_one_to_three_facts(facts):
    with pytest.raises(ValueError, match="Missing summary facts"):
        parse_summary(ROW, summary_data({"facts": facts, "compared_products": []}), False)


@pytest.mark.parametrize("bad", [
    "text", {"quote": ROW["content"]}, {"sentence": 5, "quote": ROW["content"]},
    fact(sentence="  "), fact(quote=None), fact(quote="short"),
    fact(quote="x" * 20)])
def test_summary_parse_rejects_unsupported_facts(bad):
    with pytest.raises(ValueError, match="Unsupported summary quote"):
        parse_summary(ROW, summary_data({"facts": [bad], "compared_products": []}), False)


def test_summary_parse_joins_facts_and_flags_long_summary():
    long_sentence = " ".join(["word"] * 81)
    value = {"facts": [fact(" First sentence. "), fact(long_sentence)],
             "compared_products": []}
    result = parse_summary(ROW, summary_data(value), False, prompt_version="custom-1")
    assert result["generated_summary"] == f"First sentence. {long_sentence}"
    assert result["summary_words"] == 83 and result["summary_length_review_required"]
    assert result["prompt_version"] == "custom-1"
    assert result["compared_products_status"] == "complete"
    assert result["source_hash"] == fingerprint(
        f"Title: {ROW['title']}\nContent: {ROW['content']}")
    assert not parse_summary(
        ROW, summary_data({"facts": [fact()], "compared_products": []}),
        False)["summary_length_review_required"]


@pytest.mark.parametrize("products", ["x", [{"name": "A", "quote": "q"}] * 9])
def test_summary_parse_rejects_bad_product_list(products):
    value = {"facts": [fact()], "compared_products": products}
    with pytest.raises(ValueError, match="Unexpected products"):
        parse_summary(ROW, summary_data(value), True)


@pytest.mark.parametrize("bad", ["text", {"quote": ROW["content"]},
                                 {"name": 5, "quote": ROW["content"]},
                                 {"name": " ", "quote": ROW["content"]}])
def test_summary_parse_rejects_malformed_product(bad):
    value = {"facts": [fact()], "compared_products": [bad]}
    with pytest.raises(ValueError, match="Unsupported comparison product"):
        parse_summary(ROW, summary_data(value), True)


def test_summary_parse_keeps_verified_products_and_counts_unresolved():
    value = {"facts": [fact()], "compared_products": [
        {"name": "AI system", "quote": ROW["content"]},
        {"name": "Missing name", "quote": ROW["content"]},
        {"name": "AI system", "quote": "A fabricated exact source quotation."},
        {"name": "AI system", "quote": None}]}
    result = parse_summary(ROW, summary_data(value), True)
    assert result["compared_products"] == [
        {"name": "AI system", "quote": ROW["content"], "provider_quote": ROW["content"]}]
    assert result["unresolved_compared_products"] == 3
    assert result["compared_products_status"] == "partial_unresolved"


def test_summary_parse_accepts_exactly_three_facts():
    value = {"facts": [fact()] * 3, "compared_products": []}
    assert len(parse_summary(ROW, summary_data(value), False)["support"]) == 3


def test_summary_parse_accepts_exactly_eight_products():
    product = {"name": "AI system", "quote": ROW["content"]}
    value = {"facts": [fact()], "compared_products": [product] * 8}
    result = parse_summary(ROW, summary_data(value), True)
    assert len(result["compared_products"]) == 8


def test_summary_parse_rejects_valid_products_without_comparison():
    product = {"name": "AI system", "quote": ROW["content"]}
    value = {"facts": [fact()], "compared_products": [product]}
    with pytest.raises(ValueError, match="Unexpected products"):
        parse_summary(ROW, summary_data(value), False)


def test_summary_quote_length_boundary_is_twelve_stripped_chars():
    row = {**ROW, "content": "abcdefghijkl and abcdefghijk"}
    ok = {"facts": [fact(quote="abcdefghijkl")], "compared_products": []}
    assert parse_summary(row, summary_data(ok), False)["support"][0]["quote"] == "abcdefghijkl"
    short = {"facts": [fact(quote="abcdefghijk")], "compared_products": []}
    with pytest.raises(ValueError, match="Unsupported summary quote"):
        parse_summary(row, summary_data(short), False)


def test_bad_fact_count_is_reported_before_the_row_is_read():
    value = {"facts": [], "compared_products": []}
    with pytest.raises(ValueError, match="Missing summary facts"):
        parse_summary({}, summary_data(value), False)
