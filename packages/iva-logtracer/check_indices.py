#!/usr/bin/env python3
"""检查可用的索引"""
import sys

sys.path.insert(0, 'extractors')

from kibana_client import KibanaClient

client = KibanaClient.from_env()

# 列出所有索引
print("🔍 Checking available indices...")

# 尝试搜索任意 assistant_runtime 日志
patterns = [
    "*assistant_runtime*",
    "*air_assistant*",
    "*logs-air*",
]

for pattern in patterns:
    print(f"\n📋 Pattern: {pattern}")
    try:
        result = client.search(
            query="*",
            index=pattern,
            start_time="now-1h",
            end_time="now",
            size=1
        )
        total = result.get("hits", {}).get("total", {})
        if isinstance(total, dict):
            count = total.get("value", 0)
        else:
            count = total
        print(f"   ✅ Found {count} logs")
    except Exception as e:
        print(f"   ❌ Error: {e}")
