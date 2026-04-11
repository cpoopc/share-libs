
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

    # Search last 48 hours
    start_time = "now-48h"
    end_time = "now"

    indexes = [
        "*:*-logs-air_assistant_runtime-*"
    ]
    
    print(f"\nSearching for 'Northbridge' in logs")

    for index in indexes:
        print(f"\n=== Index: {index} ===")
        try:
            # Search for the clinic keyword
            query = '"Northbridge"'
            resp = client.search(
                query=query,
                index=index,
                start_time=start_time,
                end_time=end_time,
                size=100
            )
            resp = client.search(
                query=query,
                index=index,
                start_time=start_time,
                end_time=end_time,
                size=50
            )
            hits = resp.get("hits", {}).get("hits", [])
            print(f"Found {len(hits)} hits.")
            
            sessions = {}
            for hit in hits:
                source = hit.get("_source", {})
                sid = source.get("sessionId") or source.get("session_id")
                cid = source.get("conversationId") or source.get("conversation_id")
                ts = source.get("@timestamp")
                
                if sid not in sessions:
                    sessions[sid] = {"ts": ts, "cid": cid}
            
            for sid, info in sessions.items():
                print(f"  [{info['ts']}] SID: {sid}, CID: {info['cid']}")

        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
