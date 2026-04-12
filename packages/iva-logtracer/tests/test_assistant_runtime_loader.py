import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from logtracer_extractors.iva.loaders.assistant_runtime import AssistantRuntimeLoader
from logtracer_extractors.iva.trace_context import TraceContext


def test_assistant_runtime_extracts_endpoint_session_ids() -> None:
    loader = AssistantRuntimeLoader()
    ctx = TraceContext(session_id="s-123")

    loader.extract_context_from_logs(
        ctx,
        [
            {
                "message": (
                    'Speech recognition endpoint and SRS session ID: '
                    '{"endpoint":"api-us-east-1-iva.srs.ops.ringcentral.com:443",'
                    '"srsSessionId":"srs-123"}'
                )
            },
            {
                "message": (
                    'Speech generation endpoint and SRS session ID: '
                    '{"endpoint":"api-us-east-1-iva.srs.ops.ringcentral.com:443",'
                    '"srsSessionId":"sgs-123"}'
                )
            },
        ],
    )

    assert ctx.srs_session_id == "srs-123"
    assert ctx.sgs_session_id == "sgs-123"
