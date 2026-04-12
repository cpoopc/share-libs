import os
import sys
from markdown_extractor import ConfluenceExtractor

def main():
    if len(sys.argv) < 2:
        print("Usage: fetch_page.py <page_id>")
        sys.exit(1)
        
    page_id = sys.argv[1]
    
    url = os.environ.get('CONFLUENCE_URL')
    username = os.environ.get('CONFLUENCE_USERNAME')
    token = os.environ.get('CONFLUENCE_TOKEN')
    
    if not all([url, username, token]):
        print("Missing CONFLUENCE_URL, CONFLUENCE_USERNAME, or CONFLUENCE_TOKEN env vars")
        sys.exit(1)
        
    extractor = ConfluenceExtractor(url, username, token)
    page = extractor.get_page_content(page_id)
    
    if page:
        html = page.get('body', {}).get('storage', {}).get('value', '')
        md = extractor.convert_to_markdown(html)
        print(md)
    else:
        print("Page not found")

if __name__ == "__main__":
    main()
