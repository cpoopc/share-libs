import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "agents"
    / "skills"
    / "iva-logtracer"
    / "scripts"
    / "toolcall_audit.py"
)

SPEC = importlib.util.spec_from_file_location("toolcall_audit", SCRIPT_PATH)
toolcall_audit = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(toolcall_audit)


def test_detects_transfer_mixed_outcome_message() -> None:
    findings = toolcall_audit._detect_turn_contradictions(
        "Okay, please stay with me a moment. Transferring you now, but I'm not able to complete the transfer.",
        [
            {
                "tool_name": "transfer_call",
                "status": "failed",
                "result_presence": "empty",
                "error_message": "Extension number doesn't exist",
            }
        ],
    )

    assert findings
    assert findings[0]["type"] == "mixed_transfer_outcome_messaging"


def test_detects_empty_directory_result_but_answer_claims_found() -> None:
    findings = toolcall_audit._detect_turn_contradictions(
        "I found Everth Chinchilla Corelto. Would you like me to transfer you there?",
        [
            {
                "tool_name": "air_getCompanyEmployeeList",
                "status": "success",
                "result_presence": "empty",
                "error_message": "",
            }
        ],
    )

    assert findings
    assert findings[0]["type"] == "answer_claims_found_despite_empty_tool_result"


def test_catalog_inference_marks_transfer_as_client() -> None:
    inferred = toolcall_audit._infer_tool_type_from_catalog(
        "transfer_call",
        "Transfer call to another employee by phone or extension number",
    )

    assert inferred is not None
    assert inferred["tool_type"] == "client"
    assert inferred["tool_type_source"] == "catalog"
    assert inferred["tool_type_confidence"] == "medium"


def test_apply_catalog_fallback_fills_unknown_tool_type() -> None:
    tool_calls = [
        {
            "tool_name": "air_getCompanyEmployeeList",
            "tool_type": "unknown",
            "tool_type_source": "unknown",
            "tool_type_confidence": "low",
        }
    ]
    catalog = {
        "air_getCompanyEmployeeList": {
            "tool_type": "server",
            "tool_type_source": "catalog",
            "tool_type_confidence": "medium",
        }
    }

    toolcall_audit._apply_catalog_fallback(tool_calls, catalog)

    assert tool_calls[0]["tool_type"] == "server"
    assert tool_calls[0]["tool_type_source"] == "catalog"
    assert tool_calls[0]["tool_type_confidence"] == "medium"
