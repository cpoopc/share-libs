import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from logtracer_extractors.iva.environment_profiles import (
    get_environment_profile,
    get_environment_profiles_path,
    load_environment_profile_rows,
)


def test_environment_profiles_metadata_is_loaded_from_yaml() -> None:
    profile_path = get_environment_profiles_path()
    rows = load_environment_profile_rows()

    assert profile_path.name == "environment_profiles.yaml"
    assert profile_path.exists() is True
    assert rows[0]["name"] == "lab"
    assert rows[1]["name"] == "stage"
    assert rows[1]["aliases"] == ["ops"]


def test_environment_profiles_resolve_stage_aliases() -> None:
    stage = get_environment_profile("stage")
    ops = get_environment_profile("ops")

    assert stage.name == "stage"
    assert ops.name == "stage"
    assert stage.component_backends["nca"] == "ops"
    assert stage.component_backends["cprc_srs"] == "ops"
    assert "memory_controller" not in stage.component_backends


def test_environment_profiles_resolve_production_aliases() -> None:
    production = get_environment_profile("production")
    prod = get_environment_profile("prod")

    assert production.name == "production"
    assert prod.name == "production"
    assert production.component_backends["nca"] == "ops"
    assert production.component_backends["cprc_sgs"] == "ops"
    assert "memory_controller" not in production.component_backends
