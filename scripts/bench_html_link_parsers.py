#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from time import perf_counter

from app.ingest import html as html_ingest

FIXTURE_PATH = Path("tests/fixtures/html/list_page.html")
ITERATIONS = 1000


def _bench(parser: str) -> tuple[float, int]:
    html_content = FIXTURE_PATH.read_text(encoding="utf-8")
    start = perf_counter()
    links: list[str] = []
    for _ in range(ITERATIONS):
        links = html_ingest.extract_links_from_html(
            html_content=html_content,
            base_url="https://example.com",
            list_selector="main.news-list",
            link_selector="a",
            parser=parser,
        )
    elapsed = perf_counter() - start
    return elapsed, len(links)


def main() -> None:
    print(f"fixture={FIXTURE_PATH} iterations={ITERATIONS}")

    lxml_elapsed, lxml_links = _bench("lxml")
    print(f"parser=lxml elapsed={lxml_elapsed:.4f}s links={lxml_links}")

    if html_ingest._SelectolaxHTMLParser is None:  # noqa: SLF001
        print("parser=selectolax unavailable (optional dependency not installed)")
        return

    selectolax_elapsed, selectolax_links = _bench("selectolax")
    print(
        "parser=selectolax "
        f"elapsed={selectolax_elapsed:.4f}s links={selectolax_links} "
        f"speedup_vs_lxml={lxml_elapsed / max(selectolax_elapsed, 1e-9):.2f}x"
    )


if __name__ == "__main__":
    main()
