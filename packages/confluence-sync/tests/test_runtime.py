from pathlib import Path

from cptools_confluence_sync.runtime import doctor, ensure_layout


def test_ensure_layout_creates_templates(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    result = ensure_layout()

    assert (tmp_path / "config" / "confluence-sync" / ".env").exists()
    assert (tmp_path / "config" / "confluence-sync" / ".env.production").exists()
    assert (tmp_path / "config" / "confluence-sync" / "config.yaml").exists()
    assert result["output_root"].endswith("/confluence-sync/output")


def test_doctor_uses_selected_env(monkeypatch, tmp_path: Path):
    config_root = tmp_path / "config" / "confluence-sync"
    cache_root = tmp_path / "cache"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_root))
    config_root.mkdir(parents=True, exist_ok=True)
    (config_root / "config.yaml").write_text("confluence: {url: \"${CONFLUENCE_URL}\", auth: {username: \"${CONFLUENCE_USERNAME}\", token: \"${CONFLUENCE_TOKEN}\", use_bearer: true}}\nspaces: []\nexclude: {}\nsync: {}\nupload: {}\n", encoding="utf-8")
    (config_root / ".env.production").write_text(
        "\n".join(
            [
                'CONFLUENCE_URL="https://wiki.example.com"',
                'CONFLUENCE_USERNAME="user@example.com"',
                'CONFLUENCE_TOKEN="token-value"',
            ]
        ),
        encoding="utf-8",
    )

    result = doctor(env_name="production")

    assert result["ok"] is True
    assert result["selected_env"] == "production"
