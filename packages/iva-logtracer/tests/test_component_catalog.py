from logtracer_extractors.iva.component_catalog import (
    get_component_definition,
    get_component_catalog_path,
    iter_component_definitions,
    load_component_catalog_rows,
)
from logtracer_extractors.iva.loaders import (
    AgentServiceLoader,
    AssistantRuntimeLoader,
    CPRCSGSLoader,
    CPRCSRSLoader,
    NCALoader,
)
from logtracer_extractors.nova.loaders.aig import AIGLoader
from logtracer_extractors.nova.loaders.gmg import GMGLoader


def test_component_catalog_metadata_is_loaded_from_yaml() -> None:
    catalog_path = get_component_catalog_path()
    rows = load_component_catalog_rows()

    assert catalog_path.name == "components.yaml"
    assert catalog_path.exists() is True
    assert rows[0]["name"] == "assistant_runtime"
    assert rows[0]["aliases"] == ["assistant-runtime", "air", "assistant runtime", "runtime"]
    assert rows[-1]["name"] == "cprc_sgs"


def test_component_catalog_resolves_aliases_and_matches_loader_patterns() -> None:
    by_name = {component.name: component for component in iter_component_definitions()}

    assert get_component_definition("assistant_runtime") is by_name["assistant_runtime"]
    assert get_component_definition("assistant-runtime") is by_name["assistant_runtime"]
    assert get_component_definition("air") is by_name["assistant_runtime"]
    assert get_component_definition("nca") is by_name["nca"]
    assert get_component_definition("gmg") is by_name["gmg"]

    assert by_name["assistant_runtime"].index_candidates == [AssistantRuntimeLoader().index_pattern]
    assert by_name["agent_service"].index_candidates == [AgentServiceLoader().index_pattern]
    assert by_name["nca"].index_candidates == [NCALoader().index_pattern]
    assert by_name["aig"].index_candidates == [AIGLoader().index_pattern]
    assert by_name["gmg"].index_candidates == [GMGLoader().index_pattern]
    assert by_name["cprc_srs"].index_candidates == [CPRCSRSLoader().index_pattern]
    assert by_name["cprc_sgs"].index_candidates == [CPRCSGSLoader().index_pattern]
