import tomllib
from pathlib import Path


def test_web_package_data_includes_public_templates() -> None:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    package_data = data["tool"]["setuptools"]["package-data"]["app.web"]

    assert "digest.html" in package_data
    assert "news_stats.html" in package_data
    assert "period.html" in package_data
    assert "static/css/*.css" in package_data
