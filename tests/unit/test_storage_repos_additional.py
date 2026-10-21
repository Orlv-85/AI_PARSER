from datetime import date

from app.storage.article_repo import ArticleRepo


def test_list_for_agent_delegates_to_list_for_view(monkeypatch) -> None:
    captured: dict[str, object] = {}
    expected = [("row", "key", "name")]

    def _fake_list_for_view(_self, **kwargs):
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(ArticleRepo, "list_for_view", _fake_list_for_view)
    repo = ArticleRepo(session=object())

    result = repo.list_for_agent(
        hours=24,
        limit=10,
        query="ai",
        days=7,
        sort="rank",
        min_ai_relevance=0.2,
    )

    assert result == expected
    assert captured == {
        "hours": 24,
        "limit": 10,
        "offset": 0,
        "query": "ai",
        "days": 7,
        "sort": "rank",
        "min_ai_relevance": 0.2,
    }


def test_list_for_agent_forwards_optional_date_range_and_include_content(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_list_for_view(_self, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(ArticleRepo, "list_for_view", _fake_list_for_view)
    repo = ArticleRepo(session=object())

    repo.list_for_agent(
        hours=None,
        limit=5,
        query=None,
        days=30,
        sort="published",
        date_from=date(2026, 2, 20),
        date_to=date(2026, 2, 21),
        include_content=True,
    )

    assert captured["date_from"] == date(2026, 2, 20)
    assert captured["date_to"] == date(2026, 2, 21)
    assert captured["include_content"] is True


def test_get_article_for_agent_returns_none_and_row() -> None:
    class _ExecResult:
        def __init__(self, row):
            self._row = row

        def one_or_none(self):
            return self._row

    class _Session:
        def __init__(self, row):
            self._row = row

        def execute(self, _stmt):
            return _ExecResult(self._row)

    repo_none = ArticleRepo(_Session(None))
    assert repo_none.get_article_for_agent(article_id=1) is None

    row = ("article", "src-key", "Source Name")
    repo_row = ArticleRepo(_Session(row))
    assert repo_row.get_article_for_agent(article_id=2) == row
