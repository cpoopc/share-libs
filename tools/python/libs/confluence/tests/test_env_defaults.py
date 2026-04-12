from pathlib import Path

import pytest

from cptools_confluence import env as env_module


@pytest.fixture(autouse=True)
def clear_confluence_env(monkeypatch):
    for key in (
        "CONFLUENCE_URL",
        "CONFLUENCE_USERNAME",
        "CONFLUENCE_TOKEN",
        "CONFLUENCE_USE_BEARER",
    ):
        monkeypatch.delenv(key, raising=False)


def test_get_env_defaults_reads_url_and_bearer_from_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
confluence:
  url: "https://wiki.example.com"
  auth:
    use_bearer: true
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    defaults = env_module.get_confluence_defaults()

    assert defaults.url == "https://wiki.example.com"
    assert defaults.use_bearer is True


def test_get_env_defaults_prefers_explicit_env_over_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
confluence:
  url: "https://wiki.example.com"
  auth:
    use_bearer: false
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFLUENCE_URL", "https://env.example.com")
    monkeypatch.setenv("CONFLUENCE_USE_BEARER", "true")

    defaults = env_module.get_confluence_defaults()

    assert defaults.url == "https://env.example.com"
    assert defaults.use_bearer is True
