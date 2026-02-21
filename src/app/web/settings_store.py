import json
from pathlib import Path

from app.web.models import WebUpdateSettings


class UpdateSettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> WebUpdateSettings:
        if not self.path.exists():
            return WebUpdateSettings()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return WebUpdateSettings.model_validate(payload)

    def save(self, settings: WebUpdateSettings) -> WebUpdateSettings:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(settings.model_dump(mode="json"), ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        return settings
