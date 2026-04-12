from pathlib import Path

from cptools_kibana.runtime import doctor, ensure_layout


def test_ensure_layout_creates_xdg_templates(monkeypatch, tmp_path: Path):
    config_root = tmp_path / "config"
    cache_root = tmp_path / "cache"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_root))
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_root))

    result = ensure_layout()

    assert result["config_root"] == str(config_root / "kibana-query")
    assert result["cache_root"] == str(cache_root / "kibana-query")
    assert (config_root / "kibana-query" / ".env").exists()
    assert (config_root / "kibana-query" / ".env.example").exists()
    assert (config_root / "kibana-query" / ".env.lab").exists()
    assert (config_root / "kibana-query" / ".env.production").exists()


def test_doctor_uses_selected_env_file(monkeypatch, tmp_path: Path):
    config_root = tmp_path / "config"
    cache_root = tmp_path / "cache"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_root))
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_root))

    env_file = config_root / "kibana-query" / ".env.production"
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text(
        "\n".join(
            [
                "KIBANA_URL=https://kibana.example.com",
                "KIBANA_USERNAME=test-user",
                "KIBANA_PASSWORD=test-password",
            ]
        ),
        encoding="utf-8",
    )

    result = doctor(env_name="production")

    assert result["ok"] is True
    assert result["selected_env"] == "production"
    assert result["env_file"] == str(env_file)
