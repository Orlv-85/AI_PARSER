from pathlib import Path

import pytest
import yaml

from app.config.settings import Settings


@pytest.mark.parametrize("field", [
    "semantic_admission_enabled",
    "semantic_admission_policy_version",
    "semantic_admission_prompt_version",
])
def test_production_compose_forwards_admission_settings_with_matching_defaults(field):
    compose = yaml.safe_load(Path("docker-compose.prod.yml").read_text(encoding="utf-8"))
    environment = compose["services"]["app"]["environment"]
    name = "AINEWS_" + field.upper()
    default = Settings.model_fields[field].default  # pylint: disable=unsubscriptable-object
    if field == "semantic_admission_prompt_version":
        assert environment[name] == "pilot-rubric-clarification-3"
        assert environment["AINEWS_DAILY_ENRICHMENT_ENABLED"] == "true"
        return
    if isinstance(default, bool):
        assert default is False
        default = "true"
    assert environment[name] == "${" + name + ":-" + default + "}"


def test_production_screening_requires_jev_without_enabling_local_models():
    compose = yaml.safe_load(Path("docker-compose.prod.yml").read_text(encoding="utf-8"))
    assert compose["services"]["app"]["environment"]["AINEWS_JEV_ENABLED"] == (
        "${AINEWS_JEV_ENABLED:-true}")
    assert Settings.model_fields["jev_enabled"].default is False  # pylint: disable=unsubscriptable-object


def test_production_compose_keeps_daily_signals_disabled_by_default():
    compose = yaml.safe_load(Path("docker-compose.prod.yml").read_text(encoding="utf-8"))
    environment = compose["services"]["app"]["environment"]
    # The owner flips the flag in the server's private .env; paid extraction stays off otherwise.
    assert environment["AINEWS_DAILY_SIGNALS_ENABLED"] == "${AINEWS_DAILY_SIGNALS_ENABLED:-false}"
    assert not any(key.startswith("AINEWS_DAILY_SIGNALS_") and key != "AINEWS_DAILY_SIGNALS_ENABLED"
                   for key in environment)
