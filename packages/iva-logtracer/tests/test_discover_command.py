import pytest
from pathlib import Path

from logtracer_extractors.cli import build_parser, parse_args


def test_cli_exposes_discover_subcommand() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "discover",
            "--env",
            "lab",
            "--last",
            "3d",
            "--field",
            "accountId",
            "--value",
            "17542732004",
        ]
    )

    assert args.command == "discover"
    assert args.env == "lab"
    assert args.field == "accountId"
    assert args.value == "17542732004"


def test_cli_exposes_trace_and_turn_subcommands() -> None:
    parser = build_parser()

    trace_args = parser.parse_args(
        [
            "trace",
            "s-123",
            "--env",
            "production",
            "--last",
            "24h",
            "--save-json",
        ]
    )
    turn_args = parser.parse_args(
        [
            "turn",
            "/tmp/session-dir",
            "--format",
            "markdown",
            "--html",
        ]
    )

    assert trace_args.command == "trace"
    assert trace_args.id == "s-123"
    assert trace_args.env == "production"
    assert trace_args.save_json is True
    assert turn_args.command == "turn"
    assert turn_args.session_dir == "/tmp/session-dir"
    assert turn_args.html is True


def test_cli_exposes_init_doctor_report_and_audit_subcommands() -> None:
    parser = build_parser()

    init_args = parser.parse_args(["init", "--env", "production"])
    doctor_args = parser.parse_args(["doctor", "--format", "json", "--components"])
    report_args = parser.parse_args(
        ["report", "/tmp/session-dir", "--format", "markdown", "--reported-symptom", "AIR answered wrong"]
    )
    audit_kb_args = parser.parse_args(["audit", "kb", "/tmp/session-dir"])
    audit_tools_args = parser.parse_args(["audit", "tools", "/tmp/session-a", "/tmp/session-b", "--format", "json"])

    assert init_args.command == "init"
    assert init_args.env == "production"
    assert doctor_args.command == "doctor"
    assert doctor_args.format == "json"
    assert doctor_args.components is True
    assert report_args.command == "report"
    assert report_args.session_dirs == ["/tmp/session-dir"]
    assert report_args.reported_symptom == "AIR answered wrong"
    assert audit_kb_args.command == "audit"
    assert audit_kb_args.audit_command == "kb"
    assert audit_tools_args.command == "audit"
    assert audit_tools_args.audit_command == "tools"
    assert audit_tools_args.session_dirs == ["/tmp/session-a", "/tmp/session-b"]


@pytest.mark.parametrize(
    "argv",
    [
        ["discover", "--env", "lab", "--field", "accountId"],
        ["discover", "--env", "lab", "--query", 'accountId:"1"', "--field", "accountId", "--value", "1"],
        ["discover", "--env", "lab", "--last", "3d", "--start", "2026-03-18T00:00:00Z"],
        ["discover", "--env", "lab", "--field", "accountId", "--value", "1"],
    ],
)
def test_discover_rejects_invalid_argument_combinations(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        parse_args(argv)


def test_main_dispatches_discover_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from logtracer_extractors.cli import main

    expected = (
        tmp_path / "discovery_results.json",
        tmp_path / "discovery_results.md",
    )

    def fake_run_discovery_command(args) -> int:
        assert args.command == "discover"
        assert args.output_dir == str(tmp_path)
        return 0

    monkeypatch.setattr(
        "logtracer_extractors.iva.discovery.command.run_discovery_command",
        fake_run_discovery_command,
    )
    env_file = tmp_path / ".env.lab"
    env_file.write_text("KIBANA_ES_URL=https://example.com:9200\n", encoding="utf-8")
    monkeypatch.setenv("IVA_LOGTRACER_ENV_FILE", str(env_file))

    exit_code = main(
        [
            "discover",
            "--env",
            "lab",
            "--last",
            "3d",
            "--field",
            "accountId",
            "--value",
            "17542732004",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert expected[0].name == "discovery_results.json"
    assert expected[1].name == "discovery_results.md"
    assert exit_code == 0


def test_main_dispatches_trace_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from logtracer_extractors.cli import main

    env_file = tmp_path / ".env.production"
    env_file.write_text("KIBANA_ES_URL=https://example.com:9200\n", encoding="utf-8")
    monkeypatch.setenv("IVA_LOGTRACER_ENV_FILE", str(env_file))

    captured: dict[str, object] = {}

    def fake_main(argv: list[str] | None = None) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("logtracer_extractors.iva.session_tracer.main", fake_main)

    exit_code = main(
        [
            "trace",
            "s-123",
            "--env",
            "production",
            "--last",
            "24h",
            "--save-json",
        ]
    )

    assert exit_code == 0
    assert captured["argv"] == [
        "s-123",
        "--last",
        "24h",
        "--size",
        "10000",
        "--format",
        "json",
        "--save-json",
    ]


def test_main_dispatches_turn_command(monkeypatch: pytest.MonkeyPatch) -> None:
    from logtracer_extractors.cli import main

    captured: dict[str, object] = {}

    def fake_main(argv: list[str] | None = None) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("logtracer_extractors.iva.turn.analyzer.main", fake_main)

    exit_code = main(
        [
            "turn",
            "/tmp/session-dir",
            "--format",
            "markdown",
            "--html",
        ]
    )

    assert exit_code == 0
    assert captured["argv"] == [
        "/tmp/session-dir",
        "--format",
        "markdown",
        "--html",
    ]


def test_main_dispatches_report_and_audit_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    from logtracer_extractors.cli import main

    captured: dict[str, object] = {}

    def fake_report(argv: list[str] | None = None) -> int:
        captured["report"] = argv
        return 0

    def fake_tools(argv: list[str] | None = None) -> int:
        captured["tools"] = argv
        return 0

    def fake_kb(argv: list[str] | None = None) -> int:
        captured["kb"] = argv
        return 0

    monkeypatch.setattr("logtracer_extractors.scripts.diagnostic_report.main", fake_report)
    monkeypatch.setattr("logtracer_extractors.scripts.toolcall_audit.main", fake_tools)
    monkeypatch.setattr("logtracer_extractors.scripts.kb_tool_audit.main", fake_kb)

    assert (
        main(
            [
                "report",
                "/tmp/session-dir",
                "--reported-symptom",
                "AIR answered wrong",
            ]
        )
        == 0
    )
    assert main(["audit", "tools", "/tmp/session-dir", "--format", "json"]) == 0
    assert main(["audit", "kb", "/tmp/session-dir"]) == 0

    assert captured["report"] == [
        "/tmp/session-dir",
        "--format",
        "markdown",
        "--lang",
        "zh",
        "--reported-symptom",
        "AIR answered wrong",
    ]
    assert captured["tools"] == ["/tmp/session-dir", "--format", "json"]
    assert captured["kb"] == ["/tmp/session-dir", "--tool", "air_searchCompanyKnowledgeBase"]


def test_run_discovery_command_writes_expected_output_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from logtracer_extractors.cli import parse_args
    from logtracer_extractors.iva.discovery.command import run_discovery_command

    class FakeClient:
        def count(self, **kwargs) -> int:
            return 2

        def search(self, **kwargs) -> dict:
            return {
                "hits": {
                    "hits": [
                        {
                            "sort": ["2026-03-18T00:00:01Z", "doc-1"],
                            "_source": {
                                "@timestamp": "2026-03-18T00:00:01Z",
                                "sessionId": "s-1",
                                "conversationId": "c-1",
                                "message": "Created new Conversation",
                                "accountId": "1",
                            },
                        },
                        {
                            "sort": ["2026-03-18T00:00:02Z", "doc-2"],
                            "_source": {
                                "@timestamp": "2026-03-18T00:00:02Z",
                                "sessionId": "s-1",
                                "taskId": "t-1",
                                "message": "error while forwarding",
                                "accountId": "1",
                            },
                        },
                    ]
                }
            }

    monkeypatch.setattr(
        "logtracer_extractors.iva.discovery.command.KibanaClient.from_env",
        lambda: FakeClient(),
    )

    args = parse_args(
        [
            "discover",
            "--env",
            "lab",
            "--last",
            "3d",
            "--field",
            "accountId",
            "--value",
            "1",
            "--output-dir",
            str(tmp_path),
        ]
    )

    exit_code = run_discovery_command(args)

    json_path = tmp_path / "discovery_results.json"
    markdown_path = tmp_path / "discovery_results.md"

    assert exit_code == 0
    assert json_path.exists()
    assert markdown_path.exists()
    assert '"sessionId": "s-1"' in json_path.read_text(encoding="utf-8")
    assert "error while forwarding" in markdown_path.read_text(encoding="utf-8")
    assert '"query_mode": "field_value"' in json_path.read_text(encoding="utf-8")


def test_run_discovery_command_marks_result_incomplete_when_truncated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from logtracer_extractors.cli import parse_args
    from logtracer_extractors.iva.discovery.command import run_discovery_command

    class FakeClient:
        def count(self, **kwargs) -> int:
            return 5

        def search(self, **kwargs) -> dict:
            return {
                "hits": {
                    "hits": [
                        {
                            "sort": ["2026-03-18T00:00:01Z", "doc-1"],
                            "_source": {
                                "@timestamp": "2026-03-18T00:00:01Z",
                                "sessionId": "s-1",
                                "message": "Start processing task",
                            },
                        }
                    ]
                }
            }

    monkeypatch.setattr(
        "logtracer_extractors.iva.discovery.command.KibanaClient.from_env",
        lambda: FakeClient(),
    )

    args = parse_args(
        [
            "discover",
            "--env",
            "lab",
            "--last",
            "3d",
            "--field",
            "accountId",
            "--value",
            "1",
            "--page-size",
            "1",
            "--max-pages",
            "1",
            "--output-dir",
            str(tmp_path),
        ]
    )

    run_discovery_command(args)

    json_path = tmp_path / "discovery_results.json"
    payload = json_path.read_text(encoding="utf-8")

    assert '"complete": false' in payload
