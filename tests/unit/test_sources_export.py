import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import sources as sources_config
from app.core.sources import onboarding as source_onboarding
from app.storage.models_sql import Base, Source


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_export_approved_sources_yaml_is_deterministic_and_round_trips_html_sources(
    tmp_path,
) -> None:
    session = _session()
    session.add_all(
        [
            Source(
                source_key="zulu_feed",
                name="Zulu Feed",
                type="rss",
                url="https://example.com/zulu.xml",
                enabled=True,
                fetch_interval_minutes=10,
                source_weight=0.5,
            ),
            Source(
                source_key="alpha_blog",
                name="Alpha Blog",
                type="html",
                url="https://example.com/alpha",
                enabled=True,
                fetch_interval_minutes=60,
                source_weight=1.0,
            ),
            Source(
                source_key="disabled_source",
                name="Disabled Source",
                type="rss",
                url="https://example.com/disabled.xml",
                enabled=False,
                fetch_interval_minutes=30,
                source_weight=1.5,
            ),
        ]
    )
    session.commit()

    first_snapshot = source_onboarding.export_approved_sources_yaml(session=session)
    second_snapshot = source_onboarding.export_approved_sources_yaml(session=session)
    snapshot_path = tmp_path / "exported_sources.yaml"
    snapshot_path.write_text(first_snapshot, encoding="utf-8")
    payload = yaml.safe_load(first_snapshot)
    html_source = next(item for item in payload["sources"] if item["id"] == "alpha_blog")
    round_tripped = sources_config.load_sources(snapshot_path)

    assert first_snapshot == second_snapshot
    assert [item["id"] for item in payload["sources"]] == ["alpha_blog", "zulu_feed"]
    assert html_source["type"] == "html"
    assert html_source["parser_options"] == {}
    assert [source.id for source in round_tripped] == ["alpha_blog", "zulu_feed"]
    assert [source.type for source in round_tripped] == ["html", "rss"]
    assert str(round_tripped[0].url) == "https://example.com/alpha"
    assert round_tripped[0].parser_options is not None
    assert [source.fetch_interval_minutes for source in round_tripped] == [60, 10]
    assert [source.source_weight for source in round_tripped] == [1.0, 0.5]
    assert [source.enabled for source in round_tripped] == [True, True]

    assert payload == {
        "sources": [
            {
                "id": "alpha_blog",
                "name": "Alpha Blog",
                "type": "html",
                "url": "https://example.com/alpha",
                "enabled": True,
                "fetch_interval_minutes": 60,
                "source_weight": 1.0,
                "parser_options": {},
            },
            {
                "id": "zulu_feed",
                "name": "Zulu Feed",
                "type": "rss",
                "url": "https://example.com/zulu.xml",
                "enabled": True,
                "fetch_interval_minutes": 10,
                "source_weight": 0.5,
            },
        ]
    }
