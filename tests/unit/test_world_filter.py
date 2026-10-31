"""World stream keyword filter (spec 018 item 5, W1); see src/app/core/world/world.md."""
# ruff: noqa: E501
import ast
import json
from pathlib import Path

import pytest

from app.core.world import filter as world_filter
from app.core.world.filter import (
    FINANCE_THEMES,
    REASON_FINANCE_DOMAIN,
    REASON_FINANCE_THEME,
    REASON_FINANCE_TITLE,
    REASON_NO_MATCH,
    REASON_OWN_DOMAIN,
    REASON_WEAK_NOT_AI,
    classify_title,
    filter_title,
    load_own_domains,
    own_domains_from_hosts,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "world" / "titles.jsonl"
URL = "https://example.org/news/1"


def _kept(title: str, *, url: str = URL, themes: str = "") -> bool:
    return bool(filter_title(title=title, url=url, themes=themes).kept)


@pytest.mark.parametrize(
    "title",
    [
        "Pope Leo XIV: artificial intelligence can never be a person",
        "Mujer defiende derechos de su relacion con una inteligencia artificial",
        "Les Borges relance l'intelligence artificielle municipale",
        "Historiker besorgt: Künstliche Intelligenz faelscht Dokumente",
        "Cina, film generato dall'intelligenza artificiale",
        "Нейросеть написала письмо депутатам",
        "Искусственный интеллект в школах",
        "Sztuczna inteligencja w sadach",
        "Yapay zeka ile dolandiricilik",
        "Trí tuệ nhân tạo vào lớp học",
        "人工智能进入课堂",
        "人工知能が農業を変える",
        "인공지능 교육 확대",
        "الذكاء الاصطناعي في المحاكم",
        "בינה מלאכותית בבתי חולים",
        "OpenAI sued over chatbot advice",
    ],
)
def test_filter_strong_phrases_in_many_languages(title: str) -> None:
    assert classify_title(title) == "strong"
    assert _kept(title)


def test_filter_all_caps_title_is_not_strong() -> None:
    assert classify_title("AI WILL CHANGE EVERYTHING SAYS MINISTER") == "weak"
    assert not _kept("AI WILL CHANGE EVERYTHING SAYS MINISTER")
    assert classify_title("Teachers use AI in class") == "strong"


def test_filter_cjk_title_with_ai_is_strong() -> None:
    assert classify_title("AI 泡沫破裂的前夜") == "strong"
    assert _kept("AI 泡沫破裂的前夜")


def test_filter_weak_requires_ia_ki_or_robot() -> None:
    assert classify_title("Anthropic opens an office in Tokyo") == "weak"
    result = filter_title(title="Anthropic opens an office in Tokyo", url=URL)
    assert not result.kept and result.reason == REASON_WEAK_NOT_AI
    assert not _kept("Copilot extension was compromised")
    assert not _kept("The Grok effect on the election")
    assert _kept("La IA llega a la escuela rural")
    assert _kept("KI im Kuhstall")
    assert _kept("Sidewalk delivery robots may be taxed")
    assert _kept("Algorithm decides who gets a loan")
    # IA and KI count only in capitals
    assert not _kept("Anthropic ki opens an office")


def test_filter_drops_finance_titles_and_themes() -> None:
    result = filter_title(title="Nasdaq falls as AI worries grow", url=URL)
    assert not result.kept and result.reason == REASON_FINANCE_TITLE
    assert not _kept("Reddit-Aktie bricht ein wegen KI-Suche")
    assert not _kept("天弘中证人工智能主题ETF净值下跌")
    assert _kept("Teachers use AI in class", themes="EDUCATION;TAX_FNCACT")
    for theme in FINANCE_THEMES:
        result = filter_title(title="Teachers use AI in class", url=URL, themes=f"EDUCATION;{theme}")
        assert not result.kept and result.reason == REASON_FINANCE_THEME


def test_filter_drops_finance_domains() -> None:
    for host in ("econotimes.com", "www.fool.com", "uk.finance.eastmoney.com"):
        result = filter_title(title="Teachers use AI in class", url=f"https://{host}/a")
        assert not result.kept and result.reason == REASON_FINANCE_DOMAIN, host
    assert _kept("Teachers use AI in class", url="https://notfool.com/a")


def test_filter_keeps_slguardian_org() -> None:
    assert _kept("AI threatens entry-level graduate jobs", url="https://slguardian.org/x")


def test_filter_drops_own_registrable_domains() -> None:
    own = own_domains_from_hosts(["feeds.arstechnica.com", "www.theverge.com", "openai.com"])
    for host in ("arstechnica.com", "feeds.arstechnica.com", "www.arstechnica.com", "m.theverge.com"):
        result = filter_title(title="AI in class", url=f"https://{host}/a", own_domains=own)
        assert not result.kept and result.reason == REASON_OWN_DOMAIN, host
    assert filter_title(title="AI in class", url="https://notarstechnica.com/a", own_domains=own).kept
    assert filter_title(title="AI in class", url="https://arstechnica.com.evil.example/a", own_domains=own).kept


def test_load_own_domains_cuts_feed_prefixes(tmp_path: Path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        "sources:\n"
        "  - id: a\n    url: https://feeds.arstechnica.com/arstechnica/index\n"
        "  - id: b\n    url: https://rss.example.org/feed\n"
        "  - id: c\n    url: https://microsoft.github.io/blog/feed.xml\n"
        "  - id: d\n    url: ''\n"
        "  - id: e\n    url: https://medium.com/feed/x\n"
        "  - id: f\n    url: https://feeds.feedburner.com/y\n"
        "  - id: g\n    url: https://github.com/a/b/releases.atom\n"
        "  - id: h\n    url: https://blogs.microsoft.com/ai/feed/\n",
        encoding="utf-8",
    )
    assert load_own_domains(path) == {"arstechnica.com", "example.org"}


def test_load_own_domains_reads_repo_sources() -> None:
    own = load_own_domains(ROOT / "sources.yaml")
    assert len(own) > 50
    assert "arstechnica.com" in own


def test_filter_own_domains_skip_shared_platforms() -> None:
    own = own_domains_from_hosts(["medium.com", "github.com", "feeds.feedburner.com", "blogs.microsoft.com"])
    assert own == frozenset()
    assert filter_title(title="AI in class", url="https://medium.com/@a/b", own_domains=own).kept
    assert filter_title(title="AI in class", url="https://news.microsoft.com/a", own_domains=own).kept


def test_filter_ai_token_is_a_word() -> None:
    for title in ("AIDS research gets funding", "AIIB approves a loan", "AIFF cup final", "AIRPORT delays", "AIADMK rally"):
        assert classify_title(title) is None, title
    for title in ("AI技术进入课堂", "AI-generated images flood feeds", "Kodiak AI trucks", "Teachers use AI.", "(AI) rules"):
        assert classify_title(title) == "strong", title


def test_filter_keeps_human_life_stories_with_money_words() -> None:
    for title in (
        "She shares how AI helped her son",
        "Government actions on AI in schools",
        "Реакция на ИИ в школах",
        "Акция протеста против ИИ",
        "AI stock photos flood newsrooms",
        "Фонд поддержки и инвестиции в школы с ИИ",
        "人工智能基金会成立",
        "Acciones contra la inteligencia artificial en las escuelas",
        "Azioni di protesta contro l'intelligenza artificiale",
        "Borsa in pelle e intelligenza artificiale: nuovo design",
    ):
        assert _kept(title), title


def test_filter_ia_ki_need_context() -> None:
    for title in ("Des Moines, IA wins grant", "Mi KI es tu casa", "Tour of Cedar Rapids, IA", "Anthropic KI"):
        assert not _kept(title), title
    for title in ("KI hilft bei der Diagnose", "Googles KI-Suche", "Uso de la IA en clase", "Cina, film dall'IA",
                  "Pour sauver l'IA européenne", "Eine neue KI generativ"):
        assert _kept(title), title


def test_filter_ignores_names_alexa_ai_and_automatically() -> None:
    for title in (
        "Alexa Smith wins the local election",
        "Siri and Gemini are zodiac names this year",
        "Claude Monet exhibition opens",
        "Ai Weiwei opens a show in Rome",
        "Prices change automatically on Monday",
        "Automation of the ports continues",
        "Mohammad-Ai visits the school",
    ):
        assert classify_title(title) is None, title
        assert filter_title(title=title, url=URL).reason == REASON_NO_MATCH


def _fixture_rows() -> list[dict]:
    return [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines() if line]


def test_filter_real_title_fixture() -> None:
    rows = _fixture_rows()
    assert len(rows) == 60
    assert sum(row["kept"] for row in rows) == 30
    own = own_domains_from_hosts(["techcrunch.com", "theregister.com", "theverge.com"])
    for row in rows:
        result = filter_title(title=row["title"], url=row["url"], own_domains=own)
        assert (result.kept, result.reason, result.match) == (row["kept"], row["reason"], row["match"]), row["title"]


def test_filter_has_no_io_imports() -> None:
    tree = ast.parse(Path(world_filter.__file__).read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    assert modules <= {"re", "dataclasses", "pathlib", "urllib", "yaml"}
