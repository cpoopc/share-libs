#!/usr/bin/env python3
"""
按 accountId 与时间窗口查询 assistant_runtime 日志，并可选执行完整 trace。
用法:
  python scripts/query_account_time_window.py 37439510 --start "2026-02-26T02:20:00" --end "2026-02-26T02:30:00"
  python scripts/query_account_time_window.py 37439510 --start "2026-02-26T02:20:00" --end "2026-02-26T02:30:00" --trace
"""
import argparse
import sys
from pathlib import Path

from logtracer_extractors.runtime import get_app_root

ROOT = get_app_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logtracer_extractors.kibana_client import KibanaClient

ASSISTANT_RUNTIME_INDEX = "*:*-logs-air_assistant_runtime-*"
SOURCE_INCLUDES = ["@timestamp", "message", "conversationId", "sessionId", "accountId"]


def main():
    parser = argparse.ArgumentParser(description="Query account logs in a time window")
    parser.add_argument("account_id", help="Account ID (UID), e.g. 37439510")
    parser.add_argument("--start", required=True, help="Start time (ISO), e.g. 2026-02-26T02:20:00")
    parser.add_argument("--end", required=True, help="End time (ISO), e.g. 2026-02-26T02:30:00")
    parser.add_argument("--trace", action="store_true", help="Run full session trace for found conversation(s)")
    parser.add_argument("--size", type=int, default=2000, help="Max logs (default 2000)")
    args = parser.parse_args()

    client = KibanaClient.from_env()
    result = client.search(
        query=f'accountId:"{args.account_id}"',
        index=ASSISTANT_RUNTIME_INDEX,
        start_time=args.start,
        end_time=args.end,
        size=args.size,
        source_includes=SOURCE_INCLUDES,
    )
    hits = result.get("hits", {}).get("hits", [])
    logs = [h.get("_source", {}) for h in hits]
    print(f"📥 Found {len(logs)} logs for accountId={args.account_id} in [{args.start}, {args.end}]")
    if not logs:
        print("   No logs in this window. Try different --start/--end (e.g. 10:25 UTC for 02:25 PST).")
        return 0

    # 按 conversationId 分组，取每个会话的首条时间
    by_cid = {}
    for log in logs:
        cid = log.get("conversationId")
        if cid:
            if cid not in by_cid:
                by_cid[cid] = []
            by_cid[cid].append(log)
    for cid in by_cid:
        by_cid[cid].sort(key=lambda x: x.get("@timestamp") or "")

    print(f"   Conversations: {len(by_cid)}")
    for cid, msgs in sorted(by_cid.items(), key=lambda x: x[1][0].get("@timestamp") or "", reverse=True):
        first_ts = msgs[0].get("@timestamp", "")
        sess = msgs[0].get("sessionId", "")
        print(f"   - {cid}  sessionId: {sess}  first: {first_ts}  logs: {len(msgs)}")

    if args.trace and by_cid:
        first_cid = next(iter(sorted(by_cid.keys(), key=lambda c: by_cid[c][0].get("@timestamp") or "", reverse=True)))
        print(f"\n🔍 Run full trace for this conversation:")
        print(f"   bash apps/iva_logtracer/runners/run_trace.sh {first_cid} --last 24h -n 5000")
    return 0


if __name__ == "__main__":
    sys.exit(main())
