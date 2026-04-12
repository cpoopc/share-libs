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
    env_file.write_text("KIBANA_ES_URL=https://example.com:9200\n", encoding="utf-8")
    monkeypatch.setenv("IVA_LOGTRACER_ENV_FILE", str(env_file))
    monkeypatch.setattr("logtracer_extractors.cli.KibanaClient", type("FakeClient", (), {"from_env": staticmethod(lambda: object())}))
    monkeypatch.setattr(
        "logtracer_extractors.iva.component_diagnostics.build_component_diagnostics_payload",
        lambda client, probe=True, cache_scope=None: [
            {
                "name": "assistant_runtime",
                "aliases": ["air"],
                "index_candidates": ["*:*-logs-air_assistant_runtime-*"],
                "entry_fields": ["sessionId"],
                "evidence_fields": ["message"],
                "default_enabled": True,
                "status": "matched",
                "resolved_indices": ["logs-air_assistant_runtime-2026.04.12"],
                "queryable_patterns": [],
                "probe_hit_count": 1,
            }
        ],
    )

    exit_code = cli_main(["doctor", "--env", "production", "--components", "--format", "json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["components"][0]["status"] == "matched"
    assert payload["components"][0]["resolved_indices"] == ["logs-air_assistant_runtime-2026.04.12"]
    assert payload["components"][0]["queryable_patterns"] == []
    assert payload["components"][0]["probe_hit_count"] == 1


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
    monkeypatch.setattr(
        session_tracer,
        "build_component_diagnostics_map",
        lambda *args, **kwargs: {
            "assistant_runtime": {
                "status": "matched",
                "resolved_indices": ["logs-air_assistant_runtime-2026.04.12"],
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
            "log_count": 1,
            "query": 'sessionId:"s-123"',
            "correlation_paths": [],
        },
        "gmg": {
            "status": "dependency_missing",
            "resolved_indices": ["logs-gmg-2026.04.12"],
            "queryable_patterns": [],
            "probe_hit_count": 0,
            "missing_dependencies": ["logs.nca"],
            "correlation_paths": ["nca.request_id -> gmg.log_context_RCRequestId"],
        },
    }
