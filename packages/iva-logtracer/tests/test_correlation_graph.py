from logtracer_extractors.iva.correlation_graph import (
    get_correlation_graph_path,
    get_incoming_edges,
    is_downstream_component,
    load_correlation_rows,
)


def test_correlation_graph_metadata_is_loaded_from_yaml() -> None:
    graph_path = get_correlation_graph_path()
    rows = load_correlation_rows()

    assert graph_path.name == "correlation_graph.yaml"
    assert graph_path.exists() is True
    assert rows[0] == {
        "source_component": "assistant_runtime",
        "source_field": "conversationId",
        "target_component": "agent_service",
        "target_field": "conversationId",
    }
    assert rows[-1] == {
        "source_component": "nca",
        "source_field": "request_id",
        "target_component": "gmg",
        "target_field": "log_context_RCRequestId",
    }


def test_get_incoming_edges_preserves_existing_paths() -> None:
    assert [edge.render() for edge in get_incoming_edges("gmg")] == [
        "nca.request_id -> gmg.log_context_RCRequestId"
    ]
    assert [edge.render() for edge in get_incoming_edges("cprc_srs")] == [
        "assistant_runtime.srs_session_id -> cprc_srs.message"
    ]


def test_is_downstream_component_follows_graph_reachability() -> None:
    assert is_downstream_component("assistant_runtime", "agent_service") is True
    assert is_downstream_component("assistant_runtime", "gmg") is True
    assert is_downstream_component("nca", "gmg") is True
    assert is_downstream_component("aig", "agent_service") is False
