
import os
import sys
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

try:
    from cptools_kibana import KibanaClient
except ImportError:
    project_root = "/Users/paynter.chen/Code/ai/explore/cp-tools"
    sys.path.append(os.path.join(project_root, "tools", "python", "libs", "kibana"))
    try:
        from cptools_kibana import KibanaClient
    except ImportError:
        print("Could not import cptools_kibana.")
        sys.exit(1)

def main():
    try:
        client = KibanaClient.from_env()
    except Exception as e:
        print(f"Failed to create client: {e}")
        return

    account_id = "760031072"
    clinic_name = "Northbridge Clinic"
    phone = "59000587" 
    
    # Time window: 00:49 (+08:00) is 16:49 UTC
    start_time = "2026-03-10T16:30:00Z"
    end_time = "2026-03-10T17:10:00Z"

    indexes = ["*:*"]
    
    print(f"\nSearching for variations in all indexes")
    print(f"Time Range: {start_time} to {end_time}")

    for index in indexes:
        print(f"\n=== Searching in index: {index} ===")
        try:
            # Try variations
            queries = [
                f'"{account_id}"',
                f'"{phone}"',
                f'"33159000587"',
                f'"{clinic_name}"'
            ]
            
            for q in queries:
                print(f"  Query: {q}")
                resp = client.search(
                    query=q,
                    index=index,
                    start_time=start_time,
                    end_time=end_time,
                    size=10
                )
                hits = resp.get("hits", {}).get("hits", [])
                print(f"  Found {len(hits)} hits.")
                for hit in hits:
                    source = hit.get("_source", {})
                    sid = source.get("sessionId") or source.get("session_id")
                    cid = source.get("conversationId") or source.get("conversation_id")
                    ts = source.get("@timestamp")
                    idx = hit.get("_index")
                    print(f"    [{ts}] Index: {idx}, SID: {sid}, CID: {cid}")

        except Exception as e:
            print(f"Error searching {index}: {e}")

if __name__ == "__main__":
    main()
