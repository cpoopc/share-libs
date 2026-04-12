#!/usr/bin/env python3
"""
Confluence CQL Search Tool

使用 CQL (Confluence Query Language) 搜索 Confluence 页面。

示例:
    # 全文搜索
    python cql_search.py "type=page AND text~'API'"
    
    # 搜索特定 Space
    python cql_search.py "space=IVA AND type=page" --limit 50
    
    # 输出为 JSON
    python cql_search.py "creator=currentUser()" --json
"""

import argparse
import json
import sys
from typing import Optional

from cptools_confluence import ConfluenceClient, get_client_from_env


def search_confluence(
    client: ConfluenceClient,
    query: str,
    limit: int = 25,
    space: Optional[str] = None,
) -> dict:
    """
    Execute CQL search on Confluence.
    
    Args:
        client: ConfluenceClient instance
        query: CQL query string
        limit: Maximum results to return
        space: Optional space key to restrict search
        
    Returns:
        Search results dictionary
    """
    # Add space filter if provided and not already in query
    if space and "space=" not in query.lower():
        query = f"space={space} AND ({query})"
    
    # Ensure we're searching pages by default
    if "type=" not in query.lower():
        query = f"type=page AND ({query})"
    
    return client.cql(query, limit=limit)


def format_results(results: dict, base_url: str, json_output: bool = False) -> str:
    """Format search results for display."""
    if json_output:
        return json.dumps(results, indent=2, ensure_ascii=False)
    
    pages = results.get("results", [])
    total = results.get("totalSize", len(pages))
    
    lines = [
        f"Found {total} results (showing {len(pages)})",
        "-" * 60,
    ]
    
    for item in pages:
        content = item.get("content", item)
        page_id = content.get("id", "")
        title = content.get("title", "Unknown")
        space_key = content.get("space", {}).get("key", "")
        url = f"{base_url}/pages/{page_id}"
        
        lines.append(f"📄 [{space_key}] {title}")
        lines.append(f"   ID: {page_id}")
        lines.append(f"   URL: {url}")
        lines.append("")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Search Confluence using CQL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
CQL Examples:
  type=page AND text~"keyword"           # Full-text search
  space=IVA AND title~"API"              # Search in specific space
  creator=currentUser() AND type=page    # Pages I created
  lastmodified >= now("-7d")             # Recently modified
  
More info: https://developer.atlassian.com/cloud/confluence/advanced-searching-using-cql/
        """
    )
    parser.add_argument(
        "query",
        help="CQL query string (e.g., 'text~keyword' or 'space=IVA AND type=page')"
    )
    parser.add_argument(
        "--space", "-s",
        help="Restrict search to specific space"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=25,
        help="Maximum results to return (default: 25)"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON"
    )
    
    args = parser.parse_args()
    
    try:
        client = get_client_from_env()
        
        print(f"🔍 Searching: {args.query}")
        if args.space:
            print(f"   Space: {args.space}")
        print()
        
        results = search_confluence(
            client=client,
            query=args.query,
            limit=args.limit,
            space=args.space,
        )
        
        output = format_results(results, client.base_url, args.json)
        print(output)
        
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

