"""Declared bot identity of every outgoing request; rule in usecases/ingestion/pipeline.md."""
import importlib.metadata

BOT_TOKEN = "ai-news-collector"
BOT_INFO_URL = "https://5kzt.l.time4vps.cloud/"


def _bot_version() -> str:
    try:
        return importlib.metadata.version("ai-news-collector")
    except importlib.metadata.PackageNotFoundError:
        return "0"


DEFAULT_USER_AGENT = f"{BOT_TOKEN}/{_bot_version()} (+{BOT_INFO_URL})"
