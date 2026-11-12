from datetime import date

from app.storage.article_repo import ArticleRepo, ViewFilter


def test_list_for_agent_delegates_to_list_for_view(monkeypatch) -> None:
    captured: dict[str, object] = {}
    expected = [("row", "key", "name")]

    def _fake_list_for_view(_self, view, **kwargs):
        captured.update(view=view, **kwargs)
        return expected

    monkeypatch.setattr(ArticleRepo, "list_for_view", _fake_list_for_view)
    repo = ArticleRepo(session=object())
    view = ViewFilter(hours=None, days=30, sort="published", date_from=date(2026, 2, 20),
                      date_to=date(2026, 2, 21))

    assert repo.list_for_agent(view, limit=10) == expected
    assert captured == {"view": view, "limit": 10, "offset": 0}
    repo.list_for_agent(view, limit=5, offset=3)
    assert captured == {"view": view, "limit": 5, "offset": 3}


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
