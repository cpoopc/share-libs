import os
import sys
import json
from dotenv import load_dotenv

load_dotenv()

try:
    from cptools_kibana import KibanaClient
except ImportError:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_dir))))
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

    # 1. List indices
    print("\n=== Listing Indices ===")
    try:
        indices = client.get_indices("*:*-logs-*")
        print(f"Found {len(indices)} indices.")
        # Print first 20
        for idx in indices[:20]:
            print(f"  {idx}")
    except Exception as e:
        print(f"Error listing indices: {e}")

    # 2. Search for 'exit' AND 'timeout'
    print("\n=== Searching for 'exit' AND 'timeout' in assistant_runtime ===")
    try:
        # Kibana query string syntax: +exit +timeout
        resp = client.search(
            query='+exit +timeout',
            index="*:*-logs-air_assistant_runtime-*",
            start_time="now-30d",
            end_time="now", 
            size=5
        )
        hits = resp.get("hits", {}).get("hits", [])
        print(f"Found {len(hits)} hits.")
        for hit in hits:
             source = hit.get("_source", {})
             print(f"  Time: {source.get('@timestamp')}")
             print(f"  Msg: {source.get('message')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
