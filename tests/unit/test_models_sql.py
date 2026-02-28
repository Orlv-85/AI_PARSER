from datetime import UTC, datetime

from app.storage.models_sql import ArticleAlias, Source, UTCDateTime


def test_utc_datetime_type_decorator_covers_bind_literal_and_result_paths() -> None:
    type_decorator = UTCDateTime()
    naive = datetime(2026, 2, 28, 12, 0, 0)
    aware = datetime(2026, 2, 28, 12, 0, 0, tzinfo=UTC)

    assert type_decorator.python_type is datetime
    assert type_decorator.process_bind_param(aware, None) is aware
    assert type_decorator.process_literal_param(aware, None) is aware
    assert type_decorator.process_result_value(None, None) is None
    assert type_decorator.process_result_value(naive, None) == naive.replace(tzinfo=UTC)
    assert type_decorator.process_result_value(aware, None) is aware


def test_source_and_alias_models_expose_relationship_lists() -> None:
    source = Source(
        source_key="src",
        name="Source",
        type="rss",
        url="https://example.com/feed",
    )
    alias = ArticleAlias(
        article_id=1,
        source_id=1,
        url="https://example.com/alias",
    )

    assert source.articles == []
    assert source.aliases == []
    assert alias.url == "https://example.com/alias"
