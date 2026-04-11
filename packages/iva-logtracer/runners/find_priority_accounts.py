#!/usr/bin/env python3
"""
Find accounts with priority service_tier enabled in IVA logs.
"""

import argparse
import json
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

# Add cptools_kibana to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "tools/python/libs/kibana"))

from cptools_kibana import KibanaClient, KibanaConfig


def parse_time_range(time_range: str) -> tuple[str, str]:
    """Parse time range string to Kibana format"""
    now = datetime.utcnow()

    if time_range == "last_1h":
        return "now-1h", "now"
    elif time_range == "last_24h":
        return "now-24h", "now"
    elif time_range == "last_7d":
        return "now-7d", "now"
    elif time_range == "last_30d":
        return "now-30d", "now"
    else:
        # Try to parse as "YYYY-MM-DD to YYYY-MM-DD"
        parts = time_range.split(" to ")
        if len(parts) == 2:
            return parts[0] + "T00:00:00.000Z", parts[1] + "T23:59:59.999Z"
        raise ValueError(f"Invalid time range: {time_range}")


def main():
    parser = argparse.ArgumentParser(description="Find accounts with priority service_tier")
    parser.add_argument("--kibana-url", required=True, help="Kibana URL")
    parser.add_argument("--kibana-username", required=True, help="Kibana username")
    parser.add_argument("--kibana-password", required=True, help="Kibana password")
    parser.add_argument("--time-range", default="last_24h", help="Time range (last_1h, last_24h, last_7d, last_30d)")
    parser.add_argument("--output", required=True, help="Output JSON file")
    parser.add_argument("--verify-certs", default="false", help="Verify SSL certs")
    args = parser.parse_args()

    # Initialize client
    config = KibanaConfig(
        url=args.kibana_url,
        username=args.kibana_username,
        password=args.kibana_password,
        verify_certs=args.verify_certs.lower() == "true"
    )
    client = KibanaClient(config)

    # Parse time range
    start_time, end_time = parse_time_range(args.time_range)
    print(f"Querying logs from {start_time} to {end_time}")

    # Build query - search for logs with priority service_tier in agent_service
    # Looking for logs like: "Auto-generated llm_settings: {...service_tier: 'priority'...}"
    query_str = 'message:"Auto-generated llm_settings" AND message:"priority"'
    index_pattern = "*:*-logs-air_agent_service-*"

    print(f"Searching index: {index_pattern}")
    print(f"Query: {query_str}")

    response = client.search(
        query=query_str,
        index=index_pattern,
        start_time=start_time,
        end_time=end_time,
        size=10000
    )

    hits = response.get("hits", {}).get("hits", [])
    print(f"Found {len(hits)} logs with priority service_tier")

    # Aggregate by accountId
    accounts = defaultdict(lambda: {
        "account_id": None,
        "assistant_ids": set(),
        "conversation_ids": set(),
        "request_count": 0,
        "first_seen": None,
        "last_seen": None
    })

    for hit in hits:
        source = hit.get("_source", {})
        account_id = source.get("accountId")
        assistant_id = source.get("assistantId")
        conversation_id = source.get("conversationId")
        timestamp = source.get("@timestamp")

        if account_id:
            acc = accounts[account_id]
            acc["account_id"] = account_id
            acc["request_count"] += 1
            if assistant_id:
                acc["assistant_ids"].add(assistant_id)
            if conversation_id:
                acc["conversation_ids"].add(conversation_id)
            if not acc["first_seen"] or timestamp < acc["first_seen"]:
                acc["first_seen"] = timestamp
            if not acc["last_seen"] or timestamp > acc["last_seen"]:
                acc["last_seen"] = timestamp

    # Convert sets to lists for JSON serialization
    result = {
        "query_time_range": args.time_range,
        "query": query_str,
        "index": index_pattern,
        "summary": {
            "total_accounts": len(accounts),
            "total_requests": sum(a["request_count"] for a in accounts.values())
        },
        "accounts": [
            {
                "account_id": acc["account_id"],
                "assistant_count": len(acc["assistant_ids"]),
                "conversation_count": len(acc["conversation_ids"]),
                "request_count": acc["request_count"],
                "first_seen": acc["first_seen"],
                "last_seen": acc["last_seen"]
            }
            for acc in sorted(accounts.values(), key=lambda x: x["request_count"], reverse=True)
        ]
    }

    # Save to file
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\n✅ Saved results to {output_path}")


if __name__ == "__main__":
    main()
