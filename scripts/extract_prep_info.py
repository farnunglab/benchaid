#!/usr/bin/env python3
"""
Extract prepped by/on info from Notion and update LabBook.
"""

import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error

NOTION_API_VERSION = "2022-06-28"
NOTION_BASE_URL = "https://api.notion.com/v1"

MAMMALIAN_DB = "a993dc2d-9ece-4be1-bb39-ef9dbcecdea6"
YEAST_DB = "fed91987-3071-4a79-b24f-fbcb6dc0a9a7"


def get_notion_token():
    return os.environ.get("NOTION_TOKEN") or os.environ.get("NOTION_API_KEY")


def notion_request(endpoint, method="GET", data=None):
    token = get_notion_token()
    if not token:
        print("Error: NOTION_TOKEN not set")
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


def parse_prepped_field(value):
    """Parse 'Prepped by X on YYYY-MM-DD' or similar formats."""
    if not value:
        return None, None
    
    value = value.strip()
    
    # Try pattern: "Name on YYYY-MM-DD" or "Name on Month DD, YYYY"
    # Pattern 1: "Lucas on 2024-01-15"
    match = re.match(r'^(.+?)\s+on\s+(\d{4}-\d{2}-\d{2})$', value, re.IGNORECASE)
    if match:
        return match.group(1).strip(), match.group(2)
    
    # Pattern 2: "Lucas on January 15, 2024" or "Lucas on Jan 15, 2024"
    match = re.match(r'^(.+?)\s+on\s+(\w+\s+\d{1,2},?\s+\d{4})$', value, re.IGNORECASE)
    if match:
        name = match.group(1).strip()
        date_str = match.group(2)
        # Try to parse date
        try:
            from datetime import datetime
            for fmt in ["%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y"]:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return name, dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue
        except:
            pass
        return name, None
    
    # Pattern 3: "Lucas 2024-01-15" (no "on")
    match = re.match(r'^(.+?)\s+(\d{4}-\d{2}-\d{2})$', value)
    if match:
        return match.group(1).strip(), match.group(2)
    
    # Pattern 4: Just a name
    if value and not re.search(r'\d{4}', value):
        return value, None
    
    # Pattern 5: Just a date
    match = re.match(r'^(\d{4}-\d{2}-\d{2})$', value)
    if match:
        return None, match.group(1)
    
    return value, None  # Return as name if we can't parse it


def main():
    # Fetch all proteins from both databases
    proteins = []
    
    print("Fetching mammalian proteins...", file=sys.stderr)
    mammalian_pages = query_all_pages(MAMMALIAN_DB)
    for page in mammalian_pages:
        props = page.get("properties", {})
        name = extract_property(props.get("Name"))
        notion_id = page.get("id")
        
        # Try different property name variations
        prepped_field = None
        for prop_name in props:
            if "prepped" in prop_name.lower():
                prepped_field = extract_property(props.get(prop_name))
                break
        
        if name:
            prepped_by, prepped_on = parse_prepped_field(prepped_field)
            proteins.append({
                "name": name,
                "notion_id": notion_id,
                "prepped_field_raw": prepped_field,
                "prepped_by": prepped_by,
                "prepped_on": prepped_on,
            })
    
    print("Fetching yeast proteins...", file=sys.stderr)
    yeast_pages = query_all_pages(YEAST_DB)
    for page in yeast_pages:
        props = page.get("properties", {})
        name = extract_property(props.get("Name"))
        notion_id = page.get("id")
        
        prepped_field = None
        for prop_name in props:
            if "prepped" in prop_name.lower():
                prepped_field = extract_property(props.get(prop_name))
                break
        
        if name:
            prepped_by, prepped_on = parse_prepped_field(prepped_field)
            proteins.append({
                "name": name,
                "notion_id": notion_id,
                "prepped_field_raw": prepped_field,
                "prepped_by": prepped_by,
                "prepped_on": prepped_on,
            })
    
    # Filter to only those with prepped info
    with_prep_info = [p for p in proteins if p.get("prepped_by") or p.get("prepped_on")]
    
    print(f"\nTotal proteins: {len(proteins)}", file=sys.stderr)
    print(f"With prep info: {len(with_prep_info)}", file=sys.stderr)
    
    # Output JSON
    print(json.dumps(with_prep_info, indent=2))


if __name__ == "__main__":
    main()
