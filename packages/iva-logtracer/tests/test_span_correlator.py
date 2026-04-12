from logtracer_extractors.iva.span.span_correlator import SpanCorrelator


def test_span_correlator_uses_correlation_graph_for_component_reachability() -> None:
    correlator = SpanCorrelator()

    assert correlator._is_component_call_chain("gmg", "nca") is True
    assert correlator._is_component_call_chain("agent_service", "assistant_runtime") is True
    assert correlator._is_component_call_chain("agent_service", "aig") is False
    assert correlator._is_component_call_chain("cprc_sgs", "assistant_runtime") is True
