import json
import random
from datetime import date
from pathlib import Path

import pytest

from app.core.daily_signals_entities import (
    Mention,
    Override,
    VendorClasses,
    evidence_classes,
    family_tokens,
    is_stopped,
    join,
    mention_keys,
    name_tokens,
    reconcile,
    same_family,
    selectors_conflict,
    token_prefix,
    tokens,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "daily_signals"
D = date(2026, 10, 16)


def mention(mention_id, name, entity_type="model", vendor=None, *, canonical=None, day=D,
            article_id=None, publisher="example.com", role="primary", is_new=False):
    return Mention(mention_id=mention_id, scope_day=day, article_id=article_id or mention_id,
                   publisher=publisher, name=name, canonical_name=canonical or name,
                   entity_type=entity_type, vendor=vendor, role=role, is_new=is_new)


ORGS = (mention(900, "Acme", "company"), mention(901, "Zeta", "company"))


def key(name, entity_type="model"):
    return join(name_tokens(name, entity_type))


def keys_for(target, *others):
    classes = evidence_classes([target, *others])
    return mention_keys(target, classes)


def fixture_mentions():
    rows = []
    for path in sorted(FIXTURES.glob("signals_*.json")):
        data = json.loads(path.read_text())
        day = date.fromisoformat(data["day"])
        for article in data["articles"]:
            for entity in article["entities"]:
                rows.append(Mention(
                    mention_id=len(rows) + 1, scope_day=day, article_id=article["article_id"],
                    publisher=article["publisher"], name=entity["name"],
                    canonical_name=entity["canonical"] or entity["name"],
                    entity_type=entity["type"], vendor=entity["vendor"], role=entity["role"]))
    return rows


@pytest.mark.parametrize(("left", "right", "equal"), [
    ("GPT-6", "GPT 6", True),
    ("GPT-6", "gpt6", True),
    ("Qwen 3 8B", "Qwen 38B", False),
    ("Model 1.2", "Model 12", False),
    ("pplx v1", "pplx v1.1", False),
    ("Llama 7B", "Llama 70B", False),
])
def test_join_rule(left, right, equal):
    assert (key(left) == key(right)) is equal


def test_key_examples():
    assert key("Qwen 3 8B") == "qwen3-8b"
    assert key("Qwen 38B") == "qwen38b"
    assert key("Muse Spark (open weights)") == "musespark"
    assert key("Microsoft's Decision-1") == "microsoftdecision1"
    assert key("C++ Agent") == "c++agent"
    assert key("pi0 π-Zero") == "pi0πzero"
    assert tokens("Gemini 4 Argon") == ("gemini", "4", "argon")


def test_company_rule():
    assert key("Reflection AI", "company") == "reflection"
    assert key("Z.ai", "company") == "zai"
    assert key("Acme Inc", "company") == "acme"
    assert key("AI", "company") == "ai"
    assert key("Reflection AI", "model") == "reflectionai"


@pytest.mark.parametrize("name", ["AI", "LLMs", "AI agents", "open source", "2026", "7", "x",
                                  "data center"])
def test_stoplist_and_degenerate_keys(name):
    assert is_stopped(tokens(name))


def test_specific_names_not_stopped():
    assert not is_stopped(tokens("GitHub Copilot"))
    assert not is_stopped(tokens("GPT-6"))
    assert is_stopped(tokens("Copilot"))


def test_vendor_classes_prefix_and_alias():
    classes = VendorClasses(["Google", "Google DeepMind", "Google Deepmind", "Google Cloud", "Epic",
                             "Epic Games", "BFL", "Black Forest Labs", "AWS", "Amazon", "Gemini"],
                            [("google",), ("epic", "games"), ("bfl",), ("amazon",)])
    google = ["Google", "Google DeepMind", "Google Deepmind", "Google Cloud"]
    assert {classes.of(v) for v in google} == {"google"}
    assert classes.of("Epic Games") == classes.of("Epic") == "epic"
    assert classes.of("BFL") == classes.of("Black Forest Labs")
    # Class key = shortest member (plan Decision 2 rule 6).
    assert classes.of("AWS") == classes.of("Amazon") == "aws"
    assert classes.of(None) == ""
    assert classes.of("Unknown Vendor") == ""
    # A vendor that never occurs as a company mention is not a class (CP1, gate finding 5).
    assert classes.of("Gemini") == ""


def test_base_key_independent_of_vendor_field():
    org = mention(90, "Microsoft", "company")
    with_vendor = mention(1, "Microsoft's Decision-1", vendor="Microsoft")
    without = mention(2, "Microsoft's Decision-1")
    k1 = keys_for(with_vendor, without, org)
    k2 = keys_for(without, with_vendor, org)
    assert k1.base_key == k2.base_key == "decision1"
    assert k1.vendor_key == k2.vendor_key == "microsoft"
    assert not k1.vendor_inferred and k2.vendor_inferred


def test_inferred_vendor_from_prefix():
    org = mention(90, "Reflection AI", "company")
    beam = mention(1, "Reflection Beam")
    other = mention(2, "Beam", vendor="Reflection AI")
    keys = keys_for(beam, other, org)
    assert (keys.base_key, keys.vendor_key, keys.vendor_inferred) == ("beam", "reflection", True)
    nemotron = mention(3, "NVIDIA Nemotron 3.5 Bolt 74B")
    keys = keys_for(nemotron, mention(4, "RTX", vendor="NVIDIA"), mention(91, "NVIDIA", "company"))
    assert (keys.base_key, keys.vendor_key) == ("nemotron3.5bolt74b", "nvidia")


def test_stopword_remainder_not_stripped():
    keys = keys_for(mention(1, "Meta AI", "product"), mention(2, "Muse", vendor="Meta"),
                    mention(90, "Meta", "company"))
    assert keys.base_key == "metaai"


def test_cp1_vendor_prefix_needs_org_backing_and_no_digit_remainder():
    # A product named as vendor ("Gemini") must not become a strippable vendor class.
    argon = mention(1, "Gemini 4 Argon", vendor="Google")
    feature = mention(2, "Gemini Live", "product", vendor="Gemini")
    google = mention(90, "Google", "company")
    assert keys_for(argon, feature, google).base_key == "gemini4argon"
    assert keys_for(mention(3, "Gemini Live", "product"), feature, google).base_key == "geminilive"
    # Even an org-backed class never leaves a remainder starting with a digit.
    gemini_org = mention(91, "Gemini", "company")
    assert keys_for(argon, feature, google, gemini_org).base_key == "gemini4argon"
    # Org-backed prefix with a word remainder is still stripped.
    beam = mention(4, "Reflection Beam")
    assert keys_for(beam, mention(92, "Reflection AI", "company"),
                    mention(5, "Beam", vendor="Reflection AI")).base_key == "beam"
    assert keys_for(beam, mention(5, "Beam", vendor="Reflection AI")).base_key == "reflectionbeam"


@pytest.mark.parametrize(("name", "family"), [
    ("Nemotron 3.5 Bolt 74B-A9B 24GB", "nemotron3.5bolt"),
    ("Gemma 4 E4B", "gemma4"),
    ("Llama 5 Scout 16E Instruct", "llama5scout"),
    ("pplx-decider-v1.1-27b", "pplxdeciderv1.1"),
    ("Muse Preview", "musepreview"),
    ("GGUF", "gguf"),
])
def test_family_key(name, family):
    assert join(family_tokens(tokens(name))) == family


def test_family_relation():
    org = mention(90, "NVIDIA", "company")
    bolt = mention(1, "NVIDIA Nemotron 3.5 Bolt 74B", day=date(2026, 10, 13))
    variant = mention(2, "Nemotron 3.5 Bolt 74B-A9B 24GB", vendor="NVIDIA")
    result = reconcile([org, bolt, variant])
    a = result.entities[result.assignments[1]]
    b = result.entities[result.assignments[2]]
    assert a.entity_key != b.entity_key and same_family(a, b)

    glimpse = reconcile([mention(1, "Glimpse", "company"), mention(2, "Glimpse", vendor="Elorian")])
    company, model = (glimpse.entities[glimpse.assignments[i]] for i in (1, 2))
    assert company.entity_key != model.entity_key and not same_family(company, model)

    bee = reconcile([mention(1, "Bee", "hardware"), mention(2, "Bee Frontier", "hardware")])
    small, frontier = (bee.entities[bee.assignments[i]] for i in (1, 2))
    assert not same_family(small, frontier) and token_prefix(small, frontier)

    split = reconcile([mention(1, "Atlas 7B", vendor="Acme"),
                       mention(2, "Atlas 70B", vendor="Zeta"), *ORGS])
    left, right = (split.entities[split.assignments[i]] for i in (1, 2))
    assert left.family_key == right.family_key == "atlas" and not same_family(left, right)


def test_preview_is_not_packaging():
    result = reconcile([mention(1, "Muse Spark"), mention(2, "Muse Spark Preview"),
                        mention(3, "Muse Spark Open")])
    base, preview, open_ = (result.entities[result.assignments[i]] for i in (1, 2, 3))
    assert not same_family(base, preview)
    assert token_prefix(base, open_) and token_prefix(base, preview)


def test_reconcile_is_permutation_invariant():
    rows = [
        mention(1, "Gemini 4 Argon", vendor="Google"),
        mention(2, "Gemini 4 Argon", vendor="Google DeepMind"),
        mention(3, "Gemini 4 Argon"),
        mention(4, "Google", "company"),
        mention(5, "Atlas", vendor="Acme"),
        mention(6, "Atlas", vendor="Zeta"),
        mention(7, "Atlas"),
        mention(8, "Reflection Beam"),
        mention(9, "Reflection AI", "company"),
    ]
    baseline = reconcile(rows)
    for seed in range(60):
        shuffled = list(rows)
        random.Random(seed).shuffle(shuffled)
        assert reconcile(shuffled) == baseline


def test_fixture_gemini_4_argon_is_one_entity():
    rows = fixture_mentions()
    argon = [m for m in rows if key(m.canonical_name) == "gemini4argon"]
    vendors = sorted({m.vendor or "" for m in argon})
    assert len(argon) >= 15 and "Google" in vendors and "" in vendors
    result = reconcile(rows)
    assert {result.assignments[m.mention_id] for m in argon} == {"auto:artifact:gemini4argon"}
    entity = result.entities["auto:artifact:gemini4argon"]
    assert entity.vendor_class == "google" and entity.display_name == "Gemini 4 Argon"


def test_dominant_vendor_absorbs_unknown():
    rows = [mention(i, "Atlas", vendor="Acme") for i in range(1, 10)]
    rows += [mention(10, "Atlas", vendor="Zeta"), mention(11, "Atlas"), *ORGS]
    result = reconcile(rows)
    assert result.assignments[11] == "auto:artifact:atlas:acme"
    assert result.assignments[10] == "auto:artifact:atlas:zeta"
    assert not result.entities["auto:artifact:atlas:acme"].needs_review


def test_split_vendors_share_question_entity():
    rows = [mention(i, "Atlas", vendor="Acme") for i in range(1, 6)]
    rows += [mention(i, "Atlas", vendor="Zeta") for i in range(6, 11)]
    rows += [mention(11, "Atlas"), mention(12, "Atlas"), *ORGS]
    result = reconcile(rows)
    assert result.assignments[11] == result.assignments[12] == "auto:artifact:atlas:?"
    assert result.entities["auto:artifact:atlas:?"].needs_review
    more = reconcile(rows + [mention(13, "Atlas"), mention(14, "Atlas")])
    assert set(more.entities) == set(result.entities)


def test_unbacked_vendor_does_not_split_entity():
    # Gate data: two mentions name the product line "Gemini" as vendor of Gemini 4 Argon.
    rows = [mention(i, "Gemini 4 Argon", vendor="Google") for i in range(1, 6)]
    rows += [mention(6, "Gemini 4 Argon", vendor="Gemini"), mention(7, "Gemini 4 Argon",
                                                                    vendor="Gemini"),
             mention(8, "Gemini Omni", vendor="Gemini"), mention(90, "Google", "company")]
    result = reconcile(rows)
    assert {result.assignments[i] for i in range(1, 8)} == {"auto:artifact:gemini4argon"}
    assert result.entities["auto:artifact:geminiomni"].vendor == "Gemini"


def test_entity_key_stable_when_vendor_first_named():
    before = reconcile([mention(1, "Helix World"), mention(2, "Helix World")])
    after = reconcile([mention(1, "Helix World"), mention(2, "Helix World"),
                       mention(3, "Helix World", vendor="Noiz AI")])
    assert set(before.entities) == set(after.entities) == {"auto:artifact:helixworld"}
    assert after.entities["auto:artifact:helixworld"].vendor == "Noiz AI"


def merge(override_id, source, target, *, group="artifact", source_class="", target_class=""):
    return Override(override_id=override_id, kind="merge", type_group=group, match_key=source,
                    vendor_class=source_class, target_base_key=target,
                    target_vendor_class=target_class, target_entity_key=f"manual:{override_id}")


def alias(override_id, alias_key, target, *, group="artifact"):
    return Override(override_id=override_id, kind="alias", type_group=group, match_key=alias_key,
                    vendor_class="", target_base_key=target, target_vendor_class="",
                    target_entity_key=f"manual:{override_id}")


def test_alias_override_resolves_alias_name():
    rows = [mention(1, "GPT-6", day=date(2026, 10, 1)), mention(2, "GPT-6 Astra")]
    result = reconcile(rows, [alias(1, "gpt6astra", "gpt6")])
    assert result.assignments[1] == result.assignments[2] == "manual:1"
    assert result.entities["manual:1"].first_seen_day == date(2026, 10, 1)


def test_merge_survives_vendor_and_reextraction():
    overrides = [merge(5, "clefomni", "clef")]
    rows = [mention(1, "Clef"), mention(2, "Clef-omni"), mention(3, "Clef Flash")]
    result = reconcile(rows, overrides)
    assert result.assignments[1] == result.assignments[2] == "manual:5"
    assert result.assignments[3] == "auto:artifact:clefflash"
    # A vendor named later and a re-extraction (new mention ids) keep the merge.
    rows = [mention(11, "Clef", vendor="Cloudflare"), mention(12, "Clef omni", vendor="Cloudflare"),
            mention(90, "Cloudflare", "company")]
    result = reconcile(rows, overrides)
    assert result.assignments[11] == result.assignments[12] == "manual:5"


def test_alias_precedes_merge():
    rows = [mention(1, "Orion"), mention(2, "Orion One")]
    result = reconcile(rows, [merge(1, "orionone", "atlas"), alias(2, "orionone", "orion")])
    assert result.assignments[2] == "manual:2"


def test_conflicting_selectors_refused():
    existing = [merge(1, "a", "b")]
    assert selectors_conflict(existing, merge(2, "b", "c")) == existing[0]
    assert selectors_conflict(existing, merge(3, "c", "d")) is None
    same_target = Override(override_id=4, kind="merge", type_group="artifact", match_key="e",
                           vendor_class="", target_base_key="b", target_vendor_class="",
                           target_entity_key="manual:1")
    assert selectors_conflict(existing, same_target) is None


def test_attribute_ties_are_deterministic():
    rows = [mention(1, "Zeta One"), mention(2, "ZETA ONE", "product")]
    result = reconcile(rows)
    assert reconcile(list(reversed(rows))) == result
    entity = result.entities["auto:artifact:zetaone"]
    assert entity.display_name == "ZETA ONE"
    assert entity.entity_type == "model"


def test_base_token_tie_does_not_depend_on_insertion_order():
    # F13: ("gpt", "4o") and ("gpt4o",) join to the same key; the display tokens (and so
    # `variant_of`) must not depend on which mention got the lower id.
    first = reconcile([mention(1, "GPT 4o"), mention(2, "GPT4o")])
    second = reconcile([mention(1, "GPT4o"), mention(2, "GPT 4o")])
    assert first.entities["auto:artifact:gpt4o"].base_tokens == \
        second.entities["auto:artifact:gpt4o"].base_tokens == ("gpt", "4o")


def test_glued_company_suffix_joins_vendor_class():
    # F20 (Phase 7): "LiquidAI" and "Liquid AI" are one vendor; OpenAI does not become "open".
    classes = VendorClasses(["LiquidAI", "Liquid AI", "OpenAI"],
                            [("liquid",), ("openai",)])
    assert classes.of("LiquidAI") == classes.of("Liquid AI") == "liquid"
    assert classes.of("OpenAI") == "openai"
    rows = [mention(1, "LFM2.5-2.6B", vendor="Liquid AI", day=date(2026, 8, 6)),
            mention(2, "LFM2.5-24B-A2B", vendor="LiquidAI"), mention(90, "Liquid AI", "company")]
    result = reconcile(rows)
    older, newer = (result.entities[result.assignments[i]] for i in (1, 2))
    assert older.vendor_class == newer.vendor_class == "liquid"
    assert same_family(older, newer)


def test_glued_suffix_needs_a_matching_member():
    # Cisco/Costco-style words are not split, and a glued "ai" alone keeps its own key.
    classes = VendorClasses(["Cisco", "Costco", "Sakana AI", "SakanaAI"],
                            [("cisco",), ("costco",), ("sakana",)])
    assert classes.of("Cisco") == "cisco" and classes.of("Costco") == "costco"
    assert classes.of("SakanaAI") == "sakana"


def test_trailing_plural_joins_singular_only_when_singular_exists():
    # F21 (Phase 7): "Gemini Agents" (10-08) and "Gemini agent" (10-12) are one entity.
    rows = [mention(1, "Gemini Agents", "product", day=date(2026, 10, 8)),
            mention(2, "Gemini agent", "product", day=date(2026, 10, 12))]
    result = reconcile(rows)
    assert result.assignments[1] == result.assignments[2] == "auto:artifact:geminiagent"
    assert result.entities["auto:artifact:geminiagent"].first_seen_day == date(2026, 10, 8)
    assert reconcile(list(reversed(rows))) == result
    # Without the singular in evidence nothing changes; Latin/Greek endings never fold.
    alone = reconcile([mention(1, "Claude Teams", "product")])
    assert set(alone.entities) == {"auto:artifact:claudeteams"}
    names = reconcile([mention(1, "Atlas"), mention(2, "Atla"), mention(3, "Genesis"),
                       mention(4, "Genesi"), mention(5, "Nexus"), mention(6, "Nexu")])
    assert len(set(names.assignments.values())) == 6
    # Other type groups do not fold into each other.
    mixed = reconcile([mention(1, "Bots", "company"), mention(2, "Bot", "product")])
    assert len(set(mixed.assignments.values())) == 2
