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
