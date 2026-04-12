import os
import sys
from pathlib import Path

# Add the apps/confluence dir to path
sys.path.append(str(Path(__file__).parent.parent))

# Shared Confluence client now comes from the installed `cptools-confluence` package.

from cptools_confluence import get_client_from_env
import html2text

def load_env():
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        print(f"Loading env from {env_path}")
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    os.environ[key] = value

def main():
    load_env()
    
    if len(sys.argv) < 2:
        print("Usage: fetch_page.py <page_id>")
        sys.exit(1)
        
    page_id = sys.argv[1]
    
    try:
        # get_client_from_env handles auth details details (Bearer vs Basic)
        client = get_client_from_env()
        # print(f"Connected to: {client.base_url}")
        
        page = client.get_page_by_id(page_id, expand='body.storage')
        if page:
            html = page.get('body', {}).get('storage', {}).get('value', '')
            
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.body_width = 0
            md = h.handle(html)
            print(md)
        else:
            print("Page not found")
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
