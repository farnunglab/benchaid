#!/usr/bin/env python3
"""
Extract storage buffer info from Notion proteins.
"""

import json
import os
import sys
import urllib.request

NOTION_API_VERSION = "2022-06-28"
NOTION_BASE_URL = "https://api.notion.com/v1"

MAMMALIAN_DB = ""
YEAST_DB = ""


def get_notion_token():
    return os.environ.get("NOTION_TOKEN") or os.environ.get("NOTION_API_KEY")


def notion_request(endpoint, method="GET", data=None):
    token = get_notion_token()
    if not token:
        print("Error: NOTION_TOKEN not set", file=sys.stderr)
        sys.exit(1)
    
    url = f"{NOTION_BASE_URL}/{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_API_VERSION,
        "Content-Type": "application/json",
    }
    
    req = urllib.request.Request(url, headers=headers, method=method)
    if data:
        req.data = json.dumps(data).encode("utf-8")
    
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read())


def extract_text(rich_text_array):
    if not rich_text_array:
        return ""
    return "".join(t.get("plain_text", "") for t in rich_text_array)


def extract_property(prop):
    if not prop:
        return None
    prop_type = prop.get("type", "")
    if prop_type == "title":
        return extract_text(prop.get("title", []))
    elif prop_type == "rich_text":
        return extract_text(prop.get("rich_text", []))
    return None


def query_all_pages(database_id):
    all_pages = []
    has_more = True
    start_cursor = None
    
    while has_more:
        data = {"page_size": 100}
        if start_cursor:
            data["start_cursor"] = start_cursor
        
        result = notion_request(f"databases/{database_id}/query", method="POST", data=data)
        all_pages.extend(result.get("results", []))
        has_more = result.get("has_more", False)
        start_cursor = result.get("next_cursor")
    
    return all_pages


def main():
    proteins = []
    
    print("Fetching mammalian proteins...", file=sys.stderr)
    mammalian_pages = query_all_pages(MAMMALIAN_DB)
    for page in mammalian_pages:
        props = page.get("properties", {})
        name = extract_property(props.get("Name"))
        notion_id = page.get("id")
        
        # Get storage buffer
        storage_buffer = extract_property(props.get("Storage Buffer"))
        
        if name and storage_buffer and storage_buffer.strip():
            proteins.append({
                "name": name,
                "notion_id": notion_id,
                "storage_buffer": storage_buffer.strip(),
            })
    
    print("Fetching yeast proteins...", file=sys.stderr)
    yeast_pages = query_all_pages(YEAST_DB)
    for page in yeast_pages:
        props = page.get("properties", {})
        name = extract_property(props.get("Name"))
        notion_id = page.get("id")
        
        # Get storage buffer
        storage_buffer = extract_property(props.get("Storage Buffer"))
        
        if name and storage_buffer and storage_buffer.strip():
            proteins.append({
                "name": name,
                "notion_id": notion_id,
                "storage_buffer": storage_buffer.strip(),
            })
    
    print(f"\nTotal proteins with storage buffer: {len(proteins)}", file=sys.stderr)
    print(json.dumps(proteins, indent=2))


if __name__ == "__main__":
    main()
