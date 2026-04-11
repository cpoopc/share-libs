#!/usr/bin/env python3
"""Audit KB tool usage from an iva-logtracer trace directory."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


STOP_WORDS = {
    "a",
    "an",
    "and",
    "any",
    "can",
    "do",
    "does",
    "for",
    "how",
    "i",
    "if",
    "in",
    "industry",
    "information",
    "is",
    "it",
    "let",
    "me",
    "of",
    "on",
    "or",
    "please",
    "support",
    "the",
    "to",
    "today",
    "we",
    "what",
    "you",
    "your",
}


def load_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Failed to parse {path}: {exc}") from exc
    if not isinstance(data, list):
        raise SystemExit(f"Expected JSON array in {path}")
    return [item for item in data if isinstance(item, dict)]


def decode_json_string(value: str) -> str:
    return json.loads(f'"{value}"')


def tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in STOP_WORDS and len(token) > 2
    }


def extract_tool_result(records: list[dict], tool_name: str) -> dict | None:
    pattern = re.compile(
        r'"toolResult":\{"toolCallId":"(?P<call_id>[^"]+)","name":"'
        + re.escape(tool_name)
        + r'","input":"(?P<input>(?:\\.|[^"])*)","output":"(?P<output>(?:\\.|[^"])*)","status":(?P<status>\d+)',
    )
    for index, record in enumerate(records):
        message = record.get("message", "")
        match = pattern.search(message)
        if not match:
            continue
        raw_input = decode_json_string(match.group("input"))
        raw_output = decode_json_string(match.group("output"))
        payload: dict[str, object] = {
            "record_index": index,
            "call_id": match.group("call_id"),
            "status": int(match.group("status")),
            "input_text": raw_input,
            "output_text": raw_output,
        }
        try:
            payload["input"] = json.loads(raw_input)
        except json.JSONDecodeError:
            payload["input"] = None
        try:
            payload["output"] = json.loads(raw_output)
        except json.JSONDecodeError:
            payload["output"] = None
        return payload
    return None


def extract_final_answer(
    records: list[dict], question: str | None = None, start_index: int = 0
) -> str | None:
    pattern = re.compile(
        r'"oneofKind":"end".*?"content":"(?P<content>(?:\\.|[^"])*)","toolCalls":\[\]',
    )
    candidates: list[str] = []
    for record in records[start_index:]:
        message = record.get("message", "")
        match = pattern.search(message)
        if match:
            content = decode_json_string(match.group("content"))
            if content.startswith("Hello, thanks for calling"):
                continue
            candidates.append(content)
    if not candidates:
        return None
    if question:
        question_tokens = tokenize(question)
        if question_tokens:
            scored = [
                (len(question_tokens & tokenize(candidate)), candidate)
                for candidate in candidates
            ]
            scored.sort(key=lambda item: item[0], reverse=True)
            if scored[0][0] > 0:
                return scored[0][1]
    return candidates[-1]


def extract_user_question(records: list[dict]) -> tuple[str | None, int | None]:
    pattern = re.compile(r'"producerRole":0.*?"text":"(?P<text>(?:\\.|[^"])*)"')
    for index in range(len(records) - 1, -1, -1):
        record = records[index]
        message = record.get("message", "")
        match = pattern.search(message)
        if match:
            return decode_json_string(match.group("text")), index
    return None, None


def extract_agent_service_request(records: list[dict]) -> dict | None:
    request_body = None
    completion_ms = None
    for record in records:
        message = record.get("message", "")
        if "retrieval requestBody:" in message:
            raw = message.split("retrieval requestBody:", 1)[1].strip()
            try:
                request_body = json.loads(raw)
            except json.JSONDecodeError:
                request_body = {"raw": raw}
        if "knowledge_base request completed in " in message:
            match = re.search(r"completed in (\d+)ms", message)
            if match:
                completion_ms = int(match.group(1))
    if request_body is None and completion_ms is None:
        return None
    return {"request_body": request_body, "completion_ms": completion_ms}


def extract_nca_stats(records: list[dict], tool_name: str) -> dict:
    started = False
    completed = False
    duration_ms = None
    result_length = None
    for record in records:
        message = record.get("message", "")
        if f"[Trace][Tool] Started: toolName={tool_name}" in message:
            started = True
        if f"[Tool][{tool_name}] callTool completed, success: true" in message:
            completed = True
        if "[Trace][Tool] Completed:" in message:
            duration = re.search(r"duration=(\d+)ms", message)
            length = re.search(r"resultLength=(\d+)", message)
            if duration:
                duration_ms = int(duration.group(1))
            if length:
                result_length = int(length.group(1))
    return {
        "started": started,
        "completed": completed,
        "duration_ms": duration_ms,
        "result_length": result_length,
    }


def find_matching_answer(kb_result_text: str, question: str | None) -> str | None:
    if not kb_result_text:
        return None
    if question:
        question_re = re.escape(question.strip())
        pattern = re.compile(
            rf"Question:\s*{question_re}\s*Answer:\s*(?P<answer>.+?)(?:\n\nQuestion:|\Z)",
            re.IGNORECASE | re.DOTALL,
        )
        match = pattern.search(kb_result_text)
        if match:
            return " ".join(match.group("answer").split())
    generic_pattern = re.compile(
        r"Question:\s*How do you support the tourism industry\?\s*Answer:\s*(?P<answer>.+?)(?:\n\nQuestion:|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    match = generic_pattern.search(kb_result_text)
    if match:
        return " ".join(match.group("answer").split())
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace_dir", help="Path to iva-logtracer output directory")
    parser.add_argument("--tool", default="air_searchCompanyKnowledgeBase")
    args = parser.parse_args()

    trace_dir = Path(args.trace_dir).expanduser().resolve()
    if not trace_dir.is_dir():
        raise SystemExit(f"Trace directory not found: {trace_dir}")

    assistant_runtime = load_records(trace_dir / "assistant_runtime_trace.json")
    agent_service = load_records(trace_dir / "agent_service_trace.json")
    nca = load_records(trace_dir / "nca_trace.json")

    tool_result = extract_tool_result(assistant_runtime, args.tool)
    user_question, question_index = extract_user_question(assistant_runtime)
    agent_service_request = extract_agent_service_request(agent_service)
    nca_stats = extract_nca_stats(nca, args.tool)

    final_answer = extract_final_answer(
        assistant_runtime, question=user_question, start_index=0
    )

    kb_output = {}
    if tool_result and isinstance(tool_result.get("output"), dict):
        kb_output = tool_result["output"]  # type: ignore[assignment]
    kb_result_text = kb_output.get("result", "") if isinstance(kb_output, dict) else ""
    matching_answer = find_matching_answer(kb_result_text, user_question)

    contradiction = (
        isinstance(final_answer, str)
        and "don't have any information" in final_answer.lower().replace("’", "'")
        and bool(matching_answer)
    )

    print("# KB Tool Audit")
    print()
    print(f"- Trace dir: `{trace_dir}`")
    print(f"- Tool: `{args.tool}`")
    print(f"- User question: {user_question or 'unknown'}")
    if agent_service_request and isinstance(agent_service_request.get("request_body"), dict):
        request_body = agent_service_request["request_body"]
        print(f"- Retrieval query: {request_body.get('queryText', 'unknown')}")
        print(f"- KB groups: {request_body.get('kbGroupIds', [])}")
    else:
        print("- Retrieval query: unknown")
    print(
        "- NCA tool execution: "
        f"started={nca_stats['started']} completed={nca_stats['completed']} "
        f"duration_ms={nca_stats['duration_ms']} result_length={nca_stats['result_length']}"
    )
    if agent_service_request:
        print(f"- Agent-service KB latency: {agent_service_request.get('completion_ms')}")
    print(f"- Tool result status: {tool_result.get('status') if tool_result else 'missing'}")
    print()
    print("## Final Answer")
    print(final_answer or "missing")
    print()
    print("## Matching KB Answer")
    print(matching_answer or "No exact matching Q/A found in KB result")
    print()
    print("## Assessment")
    if contradiction:
        print(
            "- CONTRADICTION: final answer claims no information, but KB returned a direct matching answer."
        )
    elif tool_result is None:
        print("- Tool result was not found in assistant runtime logs.")
    elif not nca_stats["completed"]:
        print("- KB tool did not complete successfully end-to-end.")
    else:
        print("- No contradiction detected with the current heuristic.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
