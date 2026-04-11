#!/usr/bin/env python3
"""
查询最近 N 天指定 accountId + assistantId 且含 transfer 的会话，保存到新目录并对每个会话执行完整 trace 与 AI 分析。

用法:
  python scripts/query_account_assistant_transfer.py 37439510 e2260bba-dba7-42b1-abd5-8fc02c88e5cf --last 7d
  python scripts/query_account_assistant_transfer.py 37439510 e2260bba-dba7-42b1-abd5-8fc02c88e5cf --last 7d -o ./my_audit --no-trace
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from logtracer_extractors.runtime import get_app_root, get_output_root

ROOT = get_app_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logtracer_extractors.kibana_client import KibanaClient, parse_time_range

ASSISTANT_RUNTIME_INDEX = "*:*-logs-air_assistant_runtime-*"
SOURCE_INCLUDES = ["@timestamp", "message", "conversationId", "sessionId", "accountId"]


def fetch_logs(client: KibanaClient, account_id: str, last: str, size: int):
    """拉取 assistant_runtime 关键字段."""
    start_time = parse_time_range(last)
    return client.search(
        query=f'accountId:"{account_id}"',
        index=ASSISTANT_RUNTIME_INDEX,
        start_time=start_time,
        end_time="now",
        size=size,
        source_includes=SOURCE_INCLUDES,
    )


def is_transfer_conversation(messages: list[dict]) -> bool:
    for log in messages:
        msg = (log.get("message") or "").strip()
        if "Forwarding call to" in msg or "forward: OK" in msg or "CallForwarded" in msg:
            return True
    return False


def extract_assistant_id_from_messages(messages: list[dict]) -> str | None:
    uuid_re = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    for log in messages:
        msg = (log.get("message") or "").strip()
        m = re.search(r'"assistantId"\s*:\s*"(' + uuid_re + r')"', msg)
        if m:
            return m.group(1)
    return None


def format_logs_plain(logs: dict) -> str:
    all_logs = []
    for component, component_logs in logs.items():
        for log in component_logs:
            all_logs.append({
                "component": component,
                "timestamp": log.get("@timestamp", ""),
                "message": log.get("message", ""),
            })
    all_logs.sort(key=lambda x: x["timestamp"])
    return "\n".join(f"[{log['timestamp']}] [{log['component']}] {log['message']}" for log in all_logs)


def save_trace_to_dir(output_dir: Path, result: dict, ctx) -> None:
    """将 trace 结果写入 output_dir（与 session_tracer 相同结构）."""
    output_dir.mkdir(parents=True, exist_ok=True)
    logs = result.get("logs", {})

    for component, component_logs in logs.items():
        if not component_logs:
            continue
        log_path = output_dir / f"{component}_message.log"
        lines = [
            f"[{log.get('@timestamp', '')}] {log.get('message', '')}"
            for log in sorted(component_logs, key=lambda x: x.get("@timestamp", ""))
        ]
        log_path.write_text("\n".join(lines), encoding="utf-8")

    combine_path = output_dir / "combine.log"
    combine_path.write_text(format_logs_plain(logs), encoding="utf-8")

    summary = {
        "session_id": ctx.session_id,
        "conversation_id": ctx.conversation_id,
        "srs_session_id": ctx.srs_session_id,
        "sgs_session_id": ctx.sgs_session_id,
        "summary": ctx.get_summary(),
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    try:
        from logtracer_extractors.iva.ai_extractor import save_ai_analysis_files
        save_ai_analysis_files(output_dir, logs, summary)
    except Exception as e:
        print(f"   ⚠️  AI analysis skipped: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Query account+assistant transfer conversations, save to dir, run trace+analysis",
    )
    parser.add_argument("account_id", help="Account ID (UID), e.g. 37439510")
    parser.add_argument("assistant_id", help="Assistant ID (UUID), e.g. e2260bba-dba7-42b1-abd5-8fc02c88e5cf")
    parser.add_argument("--last", "-l", default="7d", help="Time range (default: 7d)")
    parser.add_argument("--size", "-n", type=int, default=10000, help="Max assistant_runtime logs (default: 10000)")
    parser.add_argument("--output", "-o", type=Path, default=None, help="Output base dir (default: output/iva_session/audit_<account>_<assistant_short>_<last>)")
    parser.add_argument("--no-trace", action="store_true", help="Only list transfer conversations, do not run trace")
    args = parser.parse_args()

    short_aid = args.assistant_id[:8] if len(args.assistant_id) >= 8 else args.assistant_id
    default_base = get_output_root() / f"audit_{args.account_id}_{short_aid}_{args.last.replace('d', 'd')}"
    base_dir = args.output or default_base
    base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    print(f"🔍 Fetching assistant_runtime (accountId={args.account_id}, last={args.last}, size={args.size})...")
    client = KibanaClient.from_env()
    result = fetch_logs(client, args.account_id, args.last, args.size)
    hits = result.get("hits", {}).get("hits", [])
    logs = [h.get("_source", {}) for h in hits]
    print(f"   📥 Fetched {len(logs)} logs")

    by_cid = defaultdict(list)
    for log in logs:
        cid = log.get("conversationId")
        if cid:
            by_cid[cid].append(log)
    for cid in by_cid:
        by_cid[cid].sort(key=lambda x: x.get("@timestamp") or "")

    # 只保留 assistantId 匹配且含 transfer 的会话
    transfer_conversations = []
    for conversation_id, messages in by_cid.items():
        aid = extract_assistant_id_from_messages(messages)
        if aid != args.assistant_id:
            continue
        if not is_transfer_conversation(messages):
            continue
        first_ts = messages[0].get("@timestamp") if messages else None
        sess = messages[0].get("sessionId") if messages else None
        transfer_conversations.append({
            "conversationId": conversation_id,
            "sessionId": sess,
            "firstSeen": first_ts,
            "logCount": len(messages),
        })

    transfer_conversations.sort(key=lambda x: x.get("firstSeen") or "", reverse=True)
    print(f"   📋 Transfer conversations (assistantId={args.assistant_id}): {len(transfer_conversations)}")

    list_path = base_dir / "transfer_list.json"
    list_path.write_text(
        json.dumps(
            {
                "accountId": args.account_id,
                "assistantId": args.assistant_id,
                "timeRange": args.last,
                "conversations": transfer_conversations,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"   💾 {list_path}")

    if not transfer_conversations:
        print("\n✅ No transfer conversations found. Done.")
        return 0

    if args.no_trace:
        print("\n✅ Done (--no-trace: skip trace).")
        return 0

    from logtracer_extractors.iva.orchestrator import SessionTraceOrchestrator

    orchestrator = SessionTraceOrchestrator(client)
    for i, item in enumerate(transfer_conversations, 1):
        cid = item["conversationId"]
        print(f"\n   === [{i}/{len(transfer_conversations)}] Trace {cid} ===")
        try:
            ctx = orchestrator.trace_by_conversation(
                conversation_id=cid,
                time_range=args.last,
                size=5000,
            )
            res = ctx.to_result()
            session_id = ctx.session_id or "unknown"
            out_sub = base_dir / f"{session_id}-{cid}"
            save_trace_to_dir(out_sub, res, ctx)
            print(f"   ✅ {out_sub}")
        except Exception as e:
            print(f"   ⚠️  Trace failed: {e}", file=sys.stderr)

    print(f"\n📁 Output base: {base_dir}")
    print("✅ Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
