import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from logtracer_extractors.cli import build_parser, main as cli_main
from logtracer_extractors.iva import component_diagnostics
from logtracer_extractors.iva.component_diagnostics import build_component_diagnostics_map
from logtracer_extractors.iva import session_tracer
from logtracer_extractors.iva.trace_context import TraceContext


def test_cli_exposes_component_explainability_flags() -> None:
    parser = build_parser()

    doctor_args = parser.parse_args(["doctor", "--components", "--format", "json"])
    trace_args = parser.parse_args(
        [
            "trace",
            "s-123",
            "--env",
            "production",
            "--components",
            "aig",
            "gmg",
            "--explain-components",
        ]
    )

    assert doctor_args.command == "doctor"
    assert doctor_args.components is True
    assert trace_args.command == "trace"
    assert trace_args.explain_components is True


def test_cli_dispatches_trace_with_explain_components(monkeypatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env.production"
    env_file.write_text("KIBANA_ES_URL=https://example.com:9200\n", encoding="utf-8")
    monkeypatch.setenv("IVA_LOGTRACER_ENV_FILE", str(env_file))

    captured: dict[str, object] = {}

    def fake_main(argv: list[str] | None = None) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("logtracer_extractors.iva.session_tracer.main", fake_main)

    exit_code = cli_main(
        [
            "trace",
            "s-123",
            "--env",
            "production",
            "--components",
            "aig",
            "gmg",
            "--explain-components",
        ]
    )

    assert exit_code == 0
    assert captured["argv"] == [
        "s-123",
        "--last",
        "21d",
        "--size",
        "10000",
        "--format",
        "json",
        "--components",
        "aig",
        "gmg",
        "--explain-components",
    ]


def test_doctor_includes_component_catalog_in_json_output(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    env_file = tmp_path / ".env.production"
    env_file.write_text("KIBANA_ES_URL=\n", encoding="utf-8")
    monkeypatch.setenv("IVA_LOGTRACER_ENV_FILE", str(env_file))

    exit_code = cli_main(["doctor", "--env", "production", "--components", "--format", "json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    component_by_name = {component["name"]: component for component in payload["components"]}
    assert {"assistant_runtime", "agent_service", "nca", "aig", "gmg", "cprc_srs", "cprc_sgs"} <= set(component_by_name)
    assert component_by_name["assistant_runtime"]["status"] == "not_probed"


def test_doctor_includes_probed_component_status_in_json_output(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    env_file = tmp_path / ".env.production"
    env_file.write_text(
        "KIBANA_ES_URL=https://example.com:9200\nOPS_KIBANA_ES_URL=https://ops.example.com:9200\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("IVA_LOGTRACER_ENV_FILE", str(env_file))
    monkeypatch.setattr("logtracer_extractors.cli.KibanaClient", type("FakeClient", (), {"from_env": staticmethod(lambda: object())}))
    monkeypatch.setattr(
        "logtracer_extractors.iva.session_tracer._build_loader_clients",
        lambda component_names: {"nca": "ops-client", "gmg": "ops-client"},
    )
    monkeypatch.setattr(
        "logtracer_extractors.iva.session_tracer._build_component_diagnostics_for_clients",
        lambda client, component_names, loader_clients, probe=True: {
            component_name: {
                "name": component_name,
                "aliases": ["air"] if component_name == "assistant_runtime" else [],
                "index_candidates": [f"logs-{component_name}-*"],
                "entry_fields": ["sessionId"],
                "evidence_fields": ["message"],
                "default_enabled": True,
                "status": "matched",
                "resolved_indices": [f"logs-{component_name}-2026.04.12"],
                "queryable_patterns": [],
                "probe_hit_count": 1,
                "selected_backend": "ops" if component_name == "nca" else "primary",
                "routing_source": "environment_profile:production"
                if component_name == "nca"
                else "primary_default",
            }
            for component_name in component_names
        },
    )

    exit_code = cli_main(["doctor", "--env", "production", "--components", "--format", "json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    components = {entry["name"]: entry for entry in payload["components"]}
    assert components["assistant_runtime"]["status"] == "matched"
    assert components["assistant_runtime"]["selected_backend"] == "primary"
    assert components["nca"]["resolved_indices"] == ["logs-nca-2026.04.12"]
    assert components["nca"]["selected_backend"] == "ops"
    assert components["nca"]["routing_source"] == "environment_profile:production"


def test_build_component_coverage_marks_missing_dependencies() -> None:
    ctx = TraceContext(session_id="s-123", enabled_loaders={"assistant_runtime", "gmg"})
    ctx.logs["assistant_runtime"] = [{"@timestamp": "2026-04-12T00:00:00.000Z", "message": "runtime log"}]

    coverage = session_tracer.build_component_coverage(ctx, ["assistant_runtime", "gmg"])

    assert coverage["assistant_runtime"]["status"] == "matched"
    assert coverage["assistant_runtime"]["resolved_indices"] == []
    assert coverage["assistant_runtime"]["queryable_patterns"] == []
    assert coverage["gmg"]["status"] == "dependency_missing"
    assert coverage["gmg"]["missing_dependencies"] == ["logs.nca"]


def test_build_component_diagnostics_map_prewarms_components(monkeypatch) -> None:
    calls: dict[str, object] = {"prewarm": None, "resolved": []}

    class FakeResolver:
        def __init__(self, client, *, probe: bool = True) -> None:
            self.client = client
            self.probe = probe

        def prewarm_components(self, component_names, *, max_workers: int = 4) -> None:
            calls["prewarm"] = (list(component_names), max_workers)

        def resolve_component(self, component_name: str):
            calls["resolved"].append(component_name)
            return type(
                "Resolution",
                (),
                {
                    "to_dict": lambda self: {
                        "status": "matched",
                        "resolved_indices": [f"{component_name}-idx"],
                        "queryable_patterns": [],
                        "probe_hit_count": 1,
                    }
                },
            )()

    monkeypatch.setattr("logtracer_extractors.iva.component_diagnostics.IndexResolver", FakeResolver)

    diagnostics = build_component_diagnostics_map(object(), ["gmg", "aig"])

    assert calls["prewarm"] == (["gmg", "aig"], 4)
    assert list(diagnostics) == ["gmg", "aig"]
    assert calls["resolved"] == ["gmg", "aig"]


def test_build_component_diagnostics_payload_uses_fresh_persistent_cache(monkeypatch, tmp_path: Path) -> None:
    cache_root = tmp_path / "cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_root))
    now = datetime(2026, 4, 12, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(component_diagnostics, "_utcnow", lambda: now)

    cache_path = cache_root / "iva-logtracer" / "component-probes.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {
                "version": 1,
                "scopes": {
                    "production|https://example.com:9200": {
                        "cached_at": now.isoformat(),
                        "components": {
                            "assistant_runtime": {
                                "name": "assistant_runtime",
                                "status": "matched",
                                "resolved_indices": ["logs-air_assistant_runtime-2026.04.12"],
                                "queryable_patterns": [],
                                "probe_hit_count": 1,
                            }
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        component_diagnostics,
        "build_component_diagnostics_map",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should use cache")),
    )

    payload = component_diagnostics.build_component_diagnostics_payload(
        object(),
        component_names=["assistant_runtime"],
        probe=True,
        cache_scope="production|https://example.com:9200",
        cache_ttl_seconds=600,
    )

    assert payload == [
        {
            "name": "assistant_runtime",
            "status": "matched",
            "resolved_indices": ["logs-air_assistant_runtime-2026.04.12"],
            "queryable_patterns": [],
            "probe_hit_count": 1,
        }
    ]


def test_build_component_diagnostics_payload_refreshes_stale_persistent_cache(monkeypatch, tmp_path: Path) -> None:
    cache_root = tmp_path / "cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_root))
    now = datetime(2026, 4, 12, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(component_diagnostics, "_utcnow", lambda: now)

    cache_path = cache_root / "iva-logtracer" / "component-probes.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {
                "version": 1,
                "scopes": {
                    "production|https://example.com:9200": {
                        "cached_at": (now - timedelta(seconds=601)).isoformat(),
                        "components": {
                            "assistant_runtime": {
                                "name": "assistant_runtime",
                                "status": "empty",
                                "resolved_indices": [],
                                "queryable_patterns": [],
                                "probe_hit_count": 0,
                            }
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        component_diagnostics,
        "build_component_diagnostics_map",
        lambda *args, **kwargs: {
            "assistant_runtime": {
                "name": "assistant_runtime",
                "status": "matched",
                "resolved_indices": ["logs-air_assistant_runtime-2026.04.12"],
                "queryable_patterns": [],
                "probe_hit_count": 1,
            }
        },
    )

    payload = component_diagnostics.build_component_diagnostics_payload(
        object(),
        component_names=["assistant_runtime"],
        probe=True,
        cache_scope="production|https://example.com:9200",
        cache_ttl_seconds=600,
    )

    assert payload[0]["status"] == "matched"
    cached_payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert (
        cached_payload["scopes"]["production|https://example.com:9200"]["components"]["assistant_runtime"]["status"]
        == "matched"
    )


def test_build_component_coverage_uses_index_resolver_results(monkeypatch) -> None:
    class FakeResolver:
        def resolve_component(self, component_name: str):
            return type(
                "Resolution",
                (),
                {
                    "status": "matched",
                    "resolved_indices": [f"{component_name}-2026.04.12"],
                    "queryable_patterns": [],
                    "probe_hit_count": 1,
                    "error": None,
                },
            )()

    ctx = TraceContext(session_id="s-123", enabled_loaders={"assistant_runtime"})
    ctx.logs["assistant_runtime"] = [{"@timestamp": "2026-04-12T00:00:00.000Z", "message": "runtime log"}]

    coverage = session_tracer.build_component_coverage(
        ctx,
        ["assistant_runtime"],
        resolver=FakeResolver(),
    )

    assert coverage["assistant_runtime"]["status"] == "matched"
    assert coverage["assistant_runtime"]["resolved_indices"] == ["assistant_runtime-2026.04.12"]
    assert coverage["assistant_runtime"]["queryable_patterns"] == []
    assert coverage["assistant_runtime"]["probe_hit_count"] == 1
    assert coverage["assistant_runtime"]["log_count"] == 1


def test_build_component_coverage_includes_cross_component_query_evidence() -> None:
    ctx = TraceContext(
        session_id="s-123",
        conversation_id="c-123",
        enabled_loaders={"assistant_runtime", "nca", "gmg"},
    )
    ctx.logs["assistant_runtime"] = [
        {"@timestamp": "2026-04-12T00:00:00.000Z", "message": "runtime log"}
    ]
    ctx.logs["nca"] = [
        {"@timestamp": "2026-04-12T00:00:01.000Z", "message": "nca log", "request_id": "req-123"}
    ]

    coverage = session_tracer.build_component_coverage(
        ctx,
        ["assistant_runtime", "nca", "gmg"],
        component_diagnostics={
            "assistant_runtime": {
                "status": "matched",
                "resolved_indices": ["logs-air_assistant_runtime-2026.04.12"],
                "queryable_patterns": [],
                "probe_hit_count": 1,
            },
            "nca": {
                "status": "matched",
                "resolved_indices": ["logs-nca-2026.04.12"],
                "queryable_patterns": [],
                "probe_hit_count": 1,
            },
            "gmg": {
                "status": "empty",
                "resolved_indices": ["logs-gmg-2026.04.12"],
                "queryable_patterns": [],
                "probe_hit_count": 0,
            },
        },
    )

    assert coverage["assistant_runtime"]["query"] == 'sessionId:"s-123"'
    assert coverage["assistant_runtime"]["correlation_paths"] == []
    assert coverage["nca"]["query"] == 'conversation_id:"c-123"'
    assert coverage["nca"]["correlation_paths"] == [
        "assistant_runtime.conversationId -> nca.conversation_id"
    ]
    assert coverage["gmg"]["query"] == 'log_context_RCRequestId:"req-123"'
    assert coverage["gmg"]["correlation_paths"] == [
        "nca.request_id -> gmg.log_context_RCRequestId"
    ]


def test_session_tracer_writes_component_coverage_when_explaining(monkeypatch, tmp_path: Path) -> None:
    class FakeContext:
        session_id = "s-123"
        conversation_id = "c-123"
        srs_session_id = None
        sgs_session_id = None
        component_coverage = {}
        logs = {
            "assistant_runtime": [
                {"@timestamp": "2026-04-12T00:00:00.000Z", "message": "runtime log"}
            ]
        }

        def to_result(self) -> dict:
            return {
                "session_id": self.session_id,
                "conversation_id": self.conversation_id,
                "logs": self.logs,
                "summary": {"assistant_runtime": 1},
                "component_coverage": self.component_coverage,
            }

        def get_summary(self) -> dict[str, int]:
            return {"assistant_runtime": 1}

        def has(self, *keys: str) -> bool:
            return False

        def has_any(self, *keys: str) -> bool:
            return "session_id" in keys

        def is_loader_enabled(self, loader_name: str) -> bool:
            return True

    class FakeOrchestrator:
        def __init__(self, client) -> None:
            self.client = client

        def trace_by_session(self, **kwargs):
            return FakeContext()

    env_file = tmp_path / ".env.production"
    env_file.write_text("KIBANA_ES_URL=https://example.com:9200\n", encoding="utf-8")
    monkeypatch.setenv("IVA_LOGTRACER_ENV_FILE", str(env_file))
    monkeypatch.setattr(session_tracer, "DEFAULT_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(session_tracer, "KibanaClient", type("FakeClient", (), {"from_env": staticmethod(lambda: object())}))
    monkeypatch.setattr(session_tracer, "SessionTraceOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(session_tracer, "save_ai_analysis_files", lambda *args, **kwargs: {})
    monkeypatch.setattr(session_tracer, "_build_prefixed_kibana_client", lambda prefix: None)
    monkeypatch.setattr(
        session_tracer,
        "_build_component_diagnostics_for_clients",
        lambda *args, **kwargs: {
            "assistant_runtime": {
                "status": "matched",
                "resolved_indices": ["logs-air_assistant_runtime-2026.04.12"],
                "queryable_patterns": [],
                "probe_hit_count": 1,
                "selected_backend": "primary",
                "routing_source": "primary_default",
            },
            "gmg": {
                "status": "empty",
                "resolved_indices": ["logs-gmg-2026.04.12"],
                "queryable_patterns": [],
                "probe_hit_count": 0,
                "selected_backend": "primary",
                "routing_source": "primary_default",
            },
        },
    )

    exit_code = session_tracer.main(["s-123", "--components", "assistant_runtime", "gmg", "--explain-components"])

    assert exit_code == 0
    output_dirs = sorted(path for path in tmp_path.iterdir() if path.is_dir())
    assert len(output_dirs) == 1
    coverage_path = output_dirs[0] / "component_coverage.json"
    assert json.loads(coverage_path.read_text(encoding="utf-8")) == {
        "assistant_runtime": {
            "status": "matched",
            "resolved_indices": ["logs-air_assistant_runtime-2026.04.12"],
            "queryable_patterns": [],
            "probe_hit_count": 1,
            "selected_backend": "primary",
            "routing_source": "primary_default",
            "log_count": 1,
            "query": 'sessionId:"s-123"',
            "correlation_paths": [],
        },
        "gmg": {
            "status": "dependency_missing",
            "resolved_indices": ["logs-gmg-2026.04.12"],
            "queryable_patterns": [],
            "probe_hit_count": 0,
            "selected_backend": "primary",
            "routing_source": "primary_default",
            "missing_dependencies": ["logs.nca"],
            "correlation_paths": ["nca.request_id -> gmg.log_context_RCRequestId"],
        },
    }


def test_session_tracer_routes_nova_components_to_ops_client(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class FakeContext:
        session_id = "s-123"
        conversation_id = "c-123"
        srs_session_id = None
        sgs_session_id = None
        component_coverage = {}
        logs = {"assistant_runtime": []}

        def to_result(self) -> dict:
            return {
                "session_id": self.session_id,
                "conversation_id": self.conversation_id,
                "logs": self.logs,
                "summary": {},
                "component_coverage": {},
            }

        def get_summary(self) -> dict[str, int]:
            return {}

    class FakeOrchestrator:
        def __init__(self, client, *, loader_clients=None) -> None:
            captured["client"] = client
            captured["loader_clients"] = loader_clients or {}

        def trace_by_session(self, **kwargs):
            return FakeContext()

    class FakeClientFactory:
        @staticmethod
        def from_env():
            return "primary-client"

    env_file = tmp_path / ".env.stage"
    env_file.write_text(
        "\n".join(
            [
                "KIBANA_ES_URL=https://stage.example.com:9200",
                "OPS_KIBANA_ES_URL=https://kibana.ops.ringcentral.com:9200",
                "OPS_KIBANA_USERNAME=ops-user",
                "OPS_KIBANA_PASSWORD=ops-secret",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("IVA_LOGTRACER_ENV_FILE", str(env_file))
    monkeypatch.setenv("IVA_LOGTRACER_ACTIVE_ENV", "stage")
    monkeypatch.setenv("OPS_KIBANA_ES_URL", "https://kibana.ops.ringcentral.com:9200")
    monkeypatch.setenv("OPS_KIBANA_USERNAME", "ops-user")
    monkeypatch.setenv("OPS_KIBANA_PASSWORD", "ops-secret")
    monkeypatch.setattr(session_tracer, "DEFAULT_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(session_tracer, "KibanaClient", FakeClientFactory)
    monkeypatch.setattr(session_tracer, "SessionTraceOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(session_tracer, "save_ai_analysis_files", lambda *args, **kwargs: {})
    monkeypatch.setattr(session_tracer, "_build_prefixed_kibana_client", lambda prefix: f"{prefix}-client")

    exit_code = session_tracer.main(["s-123", "--components", "assistant_runtime", "nca", "aig", "gmg"])

    assert exit_code == 0
    assert captured["client"] == "primary-client"
    assert captured["loader_clients"] == {
        "nca": "OPS_KIBANA-client",
        "aig": "OPS_KIBANA-client",
        "gmg": "OPS_KIBANA-client",
    }


def test_build_loader_clients_can_route_cprc_via_env_override(monkeypatch) -> None:
    monkeypatch.setenv(
        "OPS_KIBANA_COMPONENTS",
        "nca,aig,gmg,cprc_srs,cprc_sgs",
    )
    monkeypatch.setattr(session_tracer, "_build_prefixed_kibana_client", lambda prefix: f"{prefix}-client")

    loader_clients = session_tracer._build_loader_clients(
        {"assistant_runtime", "nca", "gmg", "cprc_srs", "cprc_sgs"}
    )

    assert loader_clients == {
        "nca": "OPS_KIBANA-client",
        "gmg": "OPS_KIBANA-client",
        "cprc_srs": "OPS_KIBANA-client",
        "cprc_sgs": "OPS_KIBANA-client",
    }


def test_build_loader_clients_ignores_blank_override_and_uses_profile(monkeypatch) -> None:
    monkeypatch.setenv("OPS_KIBANA_COMPONENTS", "")
    monkeypatch.setenv("IVA_LOGTRACER_ACTIVE_ENV", "stage")
    monkeypatch.setattr(session_tracer, "_build_prefixed_kibana_client", lambda prefix: f"{prefix}-client")

    loader_clients = session_tracer._build_loader_clients(
        {"assistant_runtime", "nca", "gmg", "cprc_srs", "cprc_sgs"}
    )

    assert loader_clients == {
        "nca": "OPS_KIBANA-client",
        "gmg": "OPS_KIBANA-client",
        "cprc_srs": "OPS_KIBANA-client",
        "cprc_sgs": "OPS_KIBANA-client",
    }


def test_build_loader_clients_routes_stage_profile_components_to_ops(monkeypatch) -> None:
    monkeypatch.delenv("OPS_KIBANA_COMPONENTS", raising=False)
    monkeypatch.setenv("IVA_LOGTRACER_ACTIVE_ENV", "stage")
    monkeypatch.setattr(session_tracer, "_build_prefixed_kibana_client", lambda prefix: f"{prefix}-client")

    loader_clients = session_tracer._build_loader_clients(
        {"assistant_runtime", "nca", "gmg", "cprc_srs", "cprc_sgs"}
    )

    assert loader_clients == {
        "nca": "OPS_KIBANA-client",
        "gmg": "OPS_KIBANA-client",
        "cprc_srs": "OPS_KIBANA-client",
        "cprc_sgs": "OPS_KIBANA-client",
    }


def test_build_loader_clients_routes_production_profile_components_to_ops(monkeypatch) -> None:
    monkeypatch.delenv("OPS_KIBANA_COMPONENTS", raising=False)
    monkeypatch.setenv("IVA_LOGTRACER_ACTIVE_ENV", "production")
    monkeypatch.setattr(session_tracer, "_build_prefixed_kibana_client", lambda prefix: f"{prefix}-client")

    loader_clients = session_tracer._build_loader_clients(
        {"assistant_runtime", "nca", "gmg", "cprc_srs", "cprc_sgs"}
    )

    assert loader_clients == {
        "nca": "OPS_KIBANA-client",
        "gmg": "OPS_KIBANA-client",
        "cprc_srs": "OPS_KIBANA-client",
        "cprc_sgs": "OPS_KIBANA-client",
    }


def test_build_loader_clients_keeps_lab_profile_on_primary(monkeypatch) -> None:
    monkeypatch.delenv("OPS_KIBANA_COMPONENTS", raising=False)
    monkeypatch.setenv("IVA_LOGTRACER_ACTIVE_ENV", "lab")
    monkeypatch.setattr(session_tracer, "_build_prefixed_kibana_client", lambda prefix: f"{prefix}-client")

    loader_clients = session_tracer._build_loader_clients(
        {"assistant_runtime", "nca", "gmg", "cprc_srs", "cprc_sgs"}
    )

    assert loader_clients == {}


def test_build_loader_clients_defaults_to_nova_components_without_active_env(monkeypatch) -> None:
    monkeypatch.delenv("OPS_KIBANA_COMPONENTS", raising=False)
    monkeypatch.delenv("IVA_LOGTRACER_ACTIVE_ENV", raising=False)
    monkeypatch.setattr(session_tracer, "_build_prefixed_kibana_client", lambda prefix: f"{prefix}-client")

    loader_clients = session_tracer._build_loader_clients(
        {"assistant_runtime", "nca", "gmg", "cprc_srs", "cprc_sgs"}
    )

    assert loader_clients == {
        "nca": "OPS_KIBANA-client",
        "gmg": "OPS_KIBANA-client",
    }


def test_build_prefixed_kibana_client_reuses_primary_credentials(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, config) -> None:
            self.config = config

    monkeypatch.setenv("KIBANA_USERNAME", "primary-user")
    monkeypatch.setenv("KIBANA_PASSWORD", "primary-secret")
    monkeypatch.setenv("OPS_KIBANA_URL", "https://kibana.ops.ringcentral.com")
    monkeypatch.setattr(session_tracer, "KibanaClient", FakeClient)

    client = session_tracer._build_prefixed_kibana_client("OPS_KIBANA")

    assert client is not None
    assert client.config.url == "https://kibana.ops.ringcentral.com"
    assert client.config.username == "primary-user"
    assert client.config.password == "primary-secret"
