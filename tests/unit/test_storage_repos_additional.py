from app.storage.repos import ArticleRepo


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
        "query": "ai",
        "days": 7,
        "sort": "rank",
        "min_ai_relevance": 0.2,
    }


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
