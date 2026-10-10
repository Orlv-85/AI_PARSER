"""Evidence-constrained narratives with deterministic fallback."""

import re
from typing import Any

import httpx

from app.core.jev import _probability
from app.core.weekly_enrichment import BudgetExhausted, WeeklyEnricher


# pylint: disable=too-many-return-statements,too-many-boolean-expressions
def explain(item: dict[str, Any], enricher: WeeklyEnricher, topic: dict) -> bool:
    evidence = {row["id"]: row for row in item["evidence"]}
    packet = {"topic": topic, "metrics": {k: v for k, v in item.items()
                                          if k not in {"summary", "url", "evidence"}},
              "evidence": list(evidence.values())}
    try:
        response = enricher.deepseek(packet, (
            'Return JSON {"topic_id":"provided ID", "explanation":"short explanation", '
            '"claims":[{"text":"factual sentence", "evidence_ids":["provided ID"], '
            '"quotes":[{"evidence_id":"provided ID", "span":"exact excerpt span"}]}], '
            '"interpretation":null}. Use news attention only, never infer demand/adoption. '
            "Do not return URLs, new numbers, direction, thresholds or metric fields. "
            "Use the claims verbatim as explanation; interpretation must be null."
        ), "narrative")
        if (set(response) - {"topic_id", "explanation", "claims", "interpretation"}
                or response.get("topic_id") != item["topic_id"]
                or response.get("interpretation") is not None):
            return False
        claims = response.get("claims")
        if not isinstance(claims, list) or not 1 <= len(claims) <= 6:
            return False
        texts = []
        for claim in claims:
            if not isinstance(claim, dict) or set(claim) != {"text", "evidence_ids", "quotes"}:
                return False
            text, ids, quotes = claim["text"], claim["evidence_ids"], claim["quotes"]
            if (not isinstance(text, str) or not text.strip() or len(text) > 500
                    or not isinstance(ids, list) or not ids or any(i not in evidence for i in ids)
                    or not isinstance(quotes, list) or not quotes):
                return False
            if re.search(r"https?://|www\.", text):
                return False
            for quote in quotes:
                if (not isinstance(quote, dict) or quote.get("evidence_id") not in ids
                        or not isinstance(quote.get("span"), str) or not quote["span"].strip()
                        or quote["span"] not in evidence[quote["evidence_id"]]["excerpt"]):
                    return False
            # Restrict numeric statements to exact supplied evidence, not invented metrics.
            cited = " ".join(evidence[i]["excerpt"] for i in ids)
            if any(number not in cited for number in re.findall(r"\d+(?:\.\d+)?%?", text)):
                return False
            support = enricher.jev({"claim": text, "computed_state": item["state"],
                                    "excerpts": [evidence[i] for i in ids]}, {
                "supported": enricher.support_question(
                    "Is every factual claim supported by these excerpts and consistent with "
                    "the computed attention direction? Reject causal claims about demand, "
                    "adoption or revenue inferred only from a change in coverage.")})
            if _probability(support["supported"]["noul"]) < 0.85:
                return False
            texts.append(text)
        explanation = " ".join(texts)
        if response.get("explanation") != explanation or len(explanation) > 2000:
            return False
        item["summary"] = explanation
        item["claims"] = claims
        return True
    except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError, BudgetExhausted):
        return False
