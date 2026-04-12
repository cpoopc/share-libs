from pathlib import Path

from logtracer_extractors.runtime import (
    DEFAULT_ENV_TEMPLATE,
    get_cache_root,
    get_component_probe_cache_path,
    get_component_probe_cache_ttl_seconds,
    get_config_root,
    get_default_env_path,
    get_output_root,
    get_runtime_diagnostics,
    init_runtime_home,
)


def test_runtime_defaults_use_xdg_dirs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("IVA_LOGTRACER_HOME", raising=False)
    monkeypatch.delenv("IVA_LOGTRACER_OUTPUT_DIR", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    assert get_config_root() == (tmp_path / "config" / "iva-logtracer").resolve()
    assert get_cache_root() == (tmp_path / "cache" / "iva-logtracer").resolve()
    assert get_output_root() == (tmp_path / "cache" / "iva-logtracer" / "output" / "iva_session").resolve()
    assert get_component_probe_cache_path() == (
        tmp_path / "cache" / "iva-logtracer" / "component-probes.json"
    ).resolve()
    assert get_default_env_path("production") == (
        tmp_path / "config" / "iva-logtracer" / ".env.production"
    ).resolve()
    assert get_component_probe_cache_ttl_seconds() == 600


def test_init_runtime_home_creates_env_and_output_dirs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    paths = init_runtime_home(env_name="production")

    assert paths["config_root"].exists()
    assert paths["cache_root"].exists()
    assert paths["output_root"].exists()
    assert paths["env_path"].read_text(encoding="utf-8") == DEFAULT_ENV_TEMPLATE
    assert paths["example_path"].read_text(encoding="utf-8") == DEFAULT_ENV_TEMPLATE


def test_runtime_diagnostics_reports_required_vars(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    env_path = tmp_path / "config" / "iva-logtracer" / ".env.production"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text(
        "KIBANA_ES_URL=https://example.com:9200\nKIBANA_USERNAME=user\nKIBANA_PASSWORD=secret\n",
        encoding="utf-8",
    )

    diagnostics = get_runtime_diagnostics("production")

    assert diagnostics["env_exists"] is True
    assert diagnostics["required_vars"] == {
        "KIBANA_ES_URL": True,
        "KIBANA_USERNAME": True,
        "KIBANA_PASSWORD": True,
    }


def test_component_probe_ttl_can_be_overridden(monkeypatch) -> None:
    monkeypatch.setenv("IVA_LOGTRACER_COMPONENT_PROBE_TTL_SECONDS", "120")

    assert get_component_probe_cache_ttl_seconds() == 120
