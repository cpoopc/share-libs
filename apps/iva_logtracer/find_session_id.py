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

    conversation_id = "e86a5d69-d6b6-46e2-8f57-16b2c9736708"
    print(f"\n=== Searching for conversationId: {conversation_id} in assistant_runtime ===")
    
    try:
        # Search for the conversation ID in assistant_runtime logs
        # We look for documents containing the conversation ID
        resp = client.search(
            query=f'"{conversation_id}"',
            index="*:*-logs-air_assistant_runtime-*",
            start_time="now-7d", # Look back 7 days, adjust if needed
            end_time="now", 
            size=10
        )
        hits = resp.get("hits", {}).get("hits", [])
        print(f"Found {len(hits)} hits.")
        
        session_id = None

        for hit in hits:
             source = hit.get("_source", {})
             msg = source.get('message', '')
             current_session_id = source.get("sessionId")
             
             # Try to extract sessionId if it's a field
             if current_session_id:
                 print(f"  Found sessionId in field: {current_session_id}")
                 session_id = current_session_id
                 break
             
             # Fallback: look in message if structured (though less reliable)
             # But usually logging infrastructure extracts sessionId
             
             print(f"  Time: {source.get('@timestamp')}")
             print(f"  Msg: {msg[:200]}...") # Print first 200 chars

        if session_id:
            print(f"\n✅ Identified Session ID: {session_id}")
        else:
            print("\n❌ Could not identify Session ID from the hits.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
