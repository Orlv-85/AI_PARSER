"""Free keyword filter for world stream titles (spec 018, item 5, step W1).

No network, no database. Input is one GDELT row reduced to title, url and themes.
Behavior and tests: src/app/core/world/world.md.
"""
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import yaml

MATCH_STRONG = "strong"
MATCH_WEAK = "weak"

STRONG_PHRASES = (
    r"artificial intelligence", r"generative ai", r"machine learning", r"large language model",
    r"\bllms?\b", r"chatgpt", r"openai", r"chatbot", r"chat-bot", r"deepfake", r"deep fake",
    r"deepseek", r"neural network", r"gpt-?\d",
    r"нейросет", r"нейронн\w+ сет", r"искусственн\w+ интеллект", r"чат-?бот", r"дипфейк",
    r"штучн\w+ інтелект", r"нейромереж", r"штучны інтэлект",
    r"inteligencia artificial", r"inteligência artificial", r"intelligence artificielle",
    r"künstliche\w* intelligenz", r"intelligenza artificiale", r"sztuczn\w+ inteligencj",
    r"kunstmatige intelligentie", r"yapay zek", r"kecerdasan buatan", r"trí tuệ nhân tạo",
    r"umělá inteligence", r"inteligența artificială", r"τεχνητή νοημοσύνη",
    r"artificiell intelligens", r"kunstig intelligens", r"tekoäly", r"mesterséges intelligencia",
    r"umjetn\w+ inteligencij", r"umetn\w+ inteligenc",
    r"人工智能", r"人工智慧", r"大模型", r"生成式", r"人工知能", r"生成ai", r"인공지능",
    r"الذكاء الاصطناعي", r"هوش مصنوعی", r"בינה מלאכותית", r"ปัญญาประดิษฐ์",
    r"कृत्रिम बुद्धिमत्ता", r"एआई", r"কৃত্রিম বুদ্ধিমত্তা", r"செயற்கை நுண்ணறிவு",
)
# Weak words collide with other words or are only sometimes about AI. Names such as Alexa, Siri,
# Gemini, Claude and the stem "automat" gave false hits and are not listed.
WEAK_WORDS = (r"robot", r"algorithm", r"copilot", r"\bgrok\b", r"anthropic", r"chat bot")
# Case-sensitive tokens: "AI" is a word only in capitals.
STRONG_TOKENS = (r"\bAI\b", r"\bИИ\b", r"\bШІ\b", r"\bGPT\b", r"(?<![A-Za-z])AI(?=[-A-Z人])")
WEAK_TOKENS = (r"\bIA\b", r"\bKI\b", r"\bIAs\b", r"\bKI-", r"\bIA-")
# A weak match is kept only with one of these (IA and KI are case-sensitive).
WEAK_KEEP_RE = re.compile(r"\bIA\b|\bKI\b|(?i:robot|algorithm)")

ALL_CAPS_MIN_LETTERS = 8

FINANCE_THEMES = (
    "ECON_STOCKMARKET", "ECON_IPO", "ECON_EARNINGSREPORT", "ECON_WORLDCURRENCIES",
    "ECON_BITCOIN", "ECON_OILPRICE",
)
FINANCE_TITLE_RE = re.compile(
    r"\b(stocks?|shares|nasdaq|nyse|s&p|dow jones|wall street|valuation|earnings|price target|"
    r"etf|funding round|raises? \$|bitcoin|crypto|aktie|börse|boerse|bolsa|acciones|azioni|"
    r"actions|akcj|hisse|borsa|cổ phiếu)\b|股|基金|净值|акци|биржа|котировк|рынок|инвест",
    re.IGNORECASE,
)
# slguardian.org is a general news site and is not listed.
FINANCE_DOMAINS = (
    "econotimes.com", "boerse-express.com", "themarketsdaily.com", "247wallst.com", "fool.com",
    "marketbeat.com", "morningstar.com", "moneycontrol.com", "eastmoney.com", "investing.com",
    "seekingalpha.com", "benzinga.com", "zerohedge.com", "stocktwits.com", "tickerreport.com",
)
# Host prefixes cut when a source host becomes an own domain.
FEED_HOST_PREFIXES = ("www.", "feeds.", "feed.", "rss.")

REASON_NO_MATCH = "no_match"
REASON_WEAK_NOT_AI = "weak_not_ai"
REASON_OWN_DOMAIN = "own_domain"
REASON_FINANCE_DOMAIN = "finance_domain"
REASON_FINANCE_THEME = "finance_theme"
REASON_FINANCE_TITLE = "finance_title"

_PHRASE_RE = re.compile("|".join(STRONG_PHRASES), re.IGNORECASE)
_WEAK_WORD_RE = re.compile("|".join(WEAK_WORDS), re.IGNORECASE)
_STRONG_TOKEN_RE = re.compile("|".join(STRONG_TOKENS))
_WEAK_TOKEN_RE = re.compile("|".join(WEAK_TOKENS))


@dataclass(frozen=True)
class FilterResult:
    kept: bool
    match: str | None
    reason: str | None = None


def _is_all_caps(title: str) -> bool:
    """A headline in capitals; a title with few cased letters (a CJK title with `AI`) is not."""
    cased = [char for char in title if char.lower() != char.upper()]
    return len(cased) >= ALL_CAPS_MIN_LETTERS and title.isupper()


def classify_title(title: str) -> str | None:
    """Return `strong`, `weak` or None for the AI keywords in a title."""
    if _PHRASE_RE.search(title):
        return MATCH_STRONG
    if _STRONG_TOKEN_RE.search(title) and not _is_all_caps(title):
        return MATCH_STRONG
    weak_hit = _WEAK_WORD_RE.search(title) or _WEAK_TOKEN_RE.search(title)
    if weak_hit or _STRONG_TOKEN_RE.search(title):
        return MATCH_WEAK
    return None


def url_host(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host.removeprefix("www.")


def host_in_domains(host: str, domains: frozenset[str] | tuple[str, ...]) -> bool:
    """True when the host is one of the domains or a subdomain of one."""
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def own_domains_from_hosts(hosts: list[str]) -> frozenset[str]:
    """Own domains from source hosts: feed prefixes are cut, so subdomains match too."""
    result: set[str] = set()
    for raw in hosts:
        host = raw.lower().strip(".")
        for prefix in FEED_HOST_PREFIXES:
            if host.startswith(prefix) and host.count(".") >= 2:
                host = host.removeprefix(prefix)
                break
        if host:
            result.add(host)
    return frozenset(result)


def load_own_domains(path: Path) -> frozenset[str]:
    """Own domains of all sources in a `sources.yaml` file."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    hosts = [
        urlsplit(str(source.get("url") or "")).hostname or ""
        for source in data.get("sources", [])
        if isinstance(source, dict)
    ]
    return own_domains_from_hosts([host for host in hosts if host])


def filter_title(
    *,
    title: str,
    url: str,
    themes: str = "",
    own_domains: frozenset[str] = frozenset(),
) -> FilterResult:
    """Decide whether a GDELT row becomes a world candidate; the first failing rule is the reason."""  # noqa: E501
    match = classify_title(title)
    if match is None:
        return FilterResult(False, None, REASON_NO_MATCH)
    if match == MATCH_WEAK and not WEAK_KEEP_RE.search(title):
        return FilterResult(False, match, REASON_WEAK_NOT_AI)
    host = url_host(url)
    if host_in_domains(host, own_domains):
        return FilterResult(False, match, REASON_OWN_DOMAIN)
    if host_in_domains(host, FINANCE_DOMAINS):
        return FilterResult(False, match, REASON_FINANCE_DOMAIN)
    if any(theme in themes for theme in FINANCE_THEMES):
        return FilterResult(False, match, REASON_FINANCE_THEME)
    if FINANCE_TITLE_RE.search(title):
        return FilterResult(False, match, REASON_FINANCE_TITLE)
    return FilterResult(True, match)
