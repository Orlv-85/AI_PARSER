"""Conservative, deterministic page eligibility; dates are not eligibility signals."""
import json
import logging
import re
from urllib.parse import unquote, urlsplit

from lxml import html as lxml_html

_LOGGER = logging.getLogger(__name__)


class NonNewsPageError(ValueError):
    """A linked RSS page was positively identified as non-editorial."""


_CORPORATE = {
    "about", "about-us", "about-kobiton", "company", "team", "our-team",
    "leadership", "leadership-team", "board-of-directors", "careers", "career",
    "jobs", "contact", "contact-us", "legal", "privacy", "privacy-policy",
    "terms", "terms-of-service", "cookie-policy", "security-policy",
}
_DIRECTORIES = {
    "blog", "blogs", "news", "newsroom", "resources", "insights", "products",
    "solutions", "services", "features", "platform", "pricing", "partners",
    "customers", "integrations", "events", "login", "signup", "membership-login",
    "book-a-demo", "webinars", "podcasts", "academy",
}
_EDITORIAL = {"blog", "blogs", "news", "newsroom", "articles", "research",
              "press", "press-releases", "releases", "changelog"}
_KNOWN_LANDINGS = {
    ("autify.com", "/genesis"),
    ("autify.com", "/products/autify-genesis"),
}
_CTA = re.compile(r"\b(book (?:a )?demo|request (?:a )?demo|start (?:your |a )?free trial|"
                  r"get started|contact sales|try (?:it )?for free)\b", re.I)
_FEATURE = re.compile(r"\b(features|how it works|pricing|integrations|benefits)\b", re.I)
_EDITORIAL_TITLE = re.compile(
    r"\b(introducing|announces?|announced|launches?|launched|release|released|research|"
    r"study|benchmark|how to|guide|tutorial)\b", re.I)
_PRODUCT_SECTIONS = {"products", "solutions", "services", "features", "platform"}

# DB-managed sources do not persist CSS options. These four audited list pages
# need narrower link selection than the default whole-document anchor scan.
MANAGED_LINK_SELECTORS = {
    "https://kobiton.com/blog": 'a[href^="/blog/"], a[href^="https://kobiton.com/blog/"]',
    "https://www.qualitestgroup.com/insights/blog":
        'a[href^="/insights/blog/"], a[href^="/insights/blogs/"], '
        'a[href^="https://www.qualitestgroup.com/insights/blog/"]',
    "https://autify.com/blog": 'a[href^="/blog/"], a[href^="https://autify.com/blog/"]',
    "https://www.codium.ai/blog":
        'a[href^="/blog/"], a[href^="https://www.qodo.ai/blog/"], '
        'a[href^="https://www.codium.ai/blog/"]',
    "https://www.qodo.ai/blog": 'a[href^="/blog/"], a[href^="https://www.qodo.ai/blog/"]',
}


def path_parts(url: str) -> list[str]:
    parts = [unquote(p).casefold() for p in urlsplit(url).path.split("/") if p]
    if parts and parts[0] in {"en", "en-us", "en-gb", "fr", "de", "es", "it", "pt",
                             "pt-br", "ja", "ko", "zh", "zh-cn", "zh-tw", "ru", "pl"}:
        parts = parts[1:]
    return parts


def url_exclusion_reason(url: str) -> str | None:  # pylint: disable=too-many-return-statements
    """Match complete paths/segments, never substrings in article slugs."""
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        return "non_http_link"
    if (parsed.hostname, parsed.path.rstrip("/")) in _KNOWN_LANDINGS:
        return "verified_product_landing"
    parts = path_parts(url)
    if not parts:
        return "site_home"
    if parts[0] in _CORPORATE and (
        len(parts) == 1 or all(p in _CORPORATE for p in parts[1:])
    ):
        return "corporate_page"
    if len(parts) == 1 and parts[0] in _DIRECTORIES:
        return "directory_page"
    if parts in (["insights", "blog"], ["insights", "blogs"]):
        return "directory_page"
    if parts[0] in {"tag", "tags", "category", "categories", "author", "authors"}:
        return "taxonomy_page"
    if len(parts) >= 2 and parts[0] in _EDITORIAL and parts[1] in {
        "tag", "tags", "category", "categories", "page", "author", "authors",
    }:
        return "taxonomy_page"
    return None


def text_exclusion_reason(url: str, title: str = "", text: str = "") -> str | None:
    reason = url_exclusion_reason(url)
    if reason:
        return reason
    parts = path_parts(url)
    if any(p in _EDITORIAL for p in parts[:-1]) or _EDITORIAL_TITLE.search(title):
        return None
    body = f"{title}\n{text}"
    commercial_path = len(parts) == 1 or (parts and parts[0] in _PRODUCT_SECTIONS)
    if commercial_path and _CTA.search(body) and _FEATURE.search(body):
        return "product_landing_page"
    return None


def _schema_types(value: object) -> set[str]:
    if isinstance(value, list):
        return set().union(*(_schema_types(v) for v in value)) if value else set()
    if not isinstance(value, dict):
        return set()
    types = value.get("@type", [])
    result = {types} if isinstance(types, str) else set(types) if isinstance(types, list) else set()
    for nested in value.values():
        if isinstance(nested, (dict, list)):
            result.update(_schema_types(nested))
    return result


def html_exclusion_reason(url: str, html_content: str) -> str | None:  # pylint: disable=too-many-return-statements
    reason = url_exclusion_reason(url)
    if reason:
        return reason
    tree = lxml_html.fromstring(html_content)
    types: set[str] = set()
    for raw in tree.xpath('//script[@type="application/ld+json"]/text()'):
        try:
            types.update(_schema_types(json.loads(raw)))
        except (ValueError, TypeError):
            continue
    # Positive article evidence takes precedence over commerce cues in the body.
    if types & {"Article", "NewsArticle", "BlogPosting", "ScholarlyArticle", "TechArticle"}:
        return None
    if tree.xpath('//meta[@property="og:type" and @content="article"]'):
        return None
    if types & {"AboutPage", "ContactPage", "CollectionPage"}:
        return "non_article_schema"
    for node in tree.cssselect('nav, footer, [role="navigation"], script, style, template'):
        node.drop_tree()
    title = " ".join(tree.xpath("//h1//text()"))
    body = " ".join(" ".join(tree.xpath("//text()")).split())
    reason = text_exclusion_reason(url, title, body)
    if reason:
        return reason
    if types & {"Product", "SoftwareApplication"} and _CTA.search(body):
        return "product_landing_page"
    return None


def log_exclusion(url: str, reason: str) -> None:
    _LOGGER.info("non_news_page_excluded", extra={"url": url, "reason": reason})
