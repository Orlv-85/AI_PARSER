from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class Article(BaseModel):
    source_key: str
    title: str
    url: HttpUrl
    published_at: datetime | None = None
    summary: str | None = None
    content: str | None = None
    publication_evidence_at: datetime | None = None
    publication_date_kind: Literal["published", "updated", "unknown"] = "published"
    page_eligibility_checked: bool = Field(default=False, exclude=True)

