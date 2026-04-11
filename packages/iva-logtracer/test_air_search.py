#!/usr/bin/env python3
"""测试 assistant_runtime 查询"""

from extractors.kibana_client import KibanaClient

client = KibanaClient.from_env()

# 测试不同的字段名
queries = [
    'conversationId:"3660a5bd-0e03-4688-a16f-d850f5a0dd87"',
    'conversation_id:"3660a5bd-0e03-4688-a16f-d850f5a0dd87"',
    'message:"3660a5bd-0e03-4688-a16f-d850f5a0dd87"',
]

index = "*:*-logs-air_assistant_runtime-*"

for query in queries:
    print(f"\n🔍 Testing query: {query}")
    try:
        result = client.search(
            query=query,
            index=index,
            start_time="now-72h",
            end_time="now",
            size=10
        )
        hits = result.get("hits", {}).get("hits", [])
        print(f"   ✅ Found {len(hits)} logs")
        if hits:
            # 显示第一条日志的字段
            first_log = hits[0].get("_source", {})
            print(f"   Fields: {list(first_log.keys())[:20]}")
            break
    except Exception as e:
        print(f"   ❌ Error: {e}")

