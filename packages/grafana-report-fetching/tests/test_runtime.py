from __future__ import annotations

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cptools_grafana_report_fetching.runtime import ensure_layout, load_runtime_env, resolve_profile


def test_init_creates_expected_xdg_assets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    result = ensure_layout(force=True)

    assert (Path(result["config_root"]) / ".env").exists()
    assert (Path(result["config_root"]) / ".env.example").exists()
    assert (Path(result["config_root"]) / "profile-aliases.yaml").exists()
    assert (Path(result["config_root"]) / "core-metrics-daily.yaml").exists()


def test_resolve_profile_supports_aliases(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    ensure_layout(force=True)

    profile = resolve_profile("iva-prod")

    assert profile["profile_name"] == "iva"
    assert profile["canonical_source_id"] == "IVA"


def test_load_runtime_env_selects_named_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    ensure_layout(force=True)

    target = Path(os.environ["XDG_CONFIG_HOME"]) / "grafana-report-fetching" / ".env.production"
    target.write_text("GRAFANA_URL=https://grafana.example.com\nGRAFANA_API_KEY=test\n", encoding="utf-8")

    result = load_runtime_env(env_name="production")

    assert result["env_file"] == target
    assert os.environ["GRAFANA_URL"] == "https://grafana.example.com"
