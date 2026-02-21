from datetime import datetime

from pydantic import BaseModel, HttpUrl


class Article(BaseModel):
    source_key: str
    title: str
    url: HttpUrl
    published_at: datetime | None = None
    summary: str | None = None
    content: str | None = None

