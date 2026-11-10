import pytest

from app.core.daily.titles import digest_title


@pytest.mark.parametrize(("raw", "clean"), [
    ("pplx-decider-v1.1-27b (Hugging Face Repo)", "pplx-decider-v1.1-27b"),
    ("Introducing Clef-omni for audio (7 minute read)", "Introducing Clef-omni for audio"),
    ("agent-kit (GitHub Repo) (3 min read)", "agent-kit"),
    ("Best QA Tools Compared (2026)", "Best QA Tools Compared (2026)"),
    ("Cheap GPUs for everyone (Sponsor)", "Cheap GPUs for everyone (Sponsor)"),
    ("(5 minute read)", "(5 minute read)"),
])
def test_digest_title_strips_only_aggregator_decorations(raw, clean):
    assert digest_title(raw) == clean
