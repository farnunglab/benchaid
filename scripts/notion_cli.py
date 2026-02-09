#!/usr/bin/env python3
"""
Notion CLI - Read and search Notion pages, databases, and blocks

Usage:
    notion_cli.py search <query>                    Search pages and databases
    notion_cli.py page <page_id>                    Show page properties
    notion_cli.py read <page_id>                    Read page content (blocks)
    notion_cli.py databases                         List all databases
    notion_cli.py db <database_id>                  Show database schema
    notion_cli.py query <database_id> [--filter]    Query a database
    notion_cli.py block <block_id>                  Read a specific block
    notion_cli.py download <page_id> [--output]     Download files from a page
    notion_cli.py files <database_id> <name>        Download files by entry name
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, List, Dict, Any

# Notion configuration
NOTION_API_VERSION = "2022-06-28"
NOTION_BASE_URL = "https://api.notion.com/v1"


def get_notion_token() -> Optional[str]:
    """Get Notion token from environment, trying shell source if needed."""
    # Try NOTION_TOKEN first, then NOTION_API_KEY
    token = os.environ.get("NOTION_TOKEN") or os.environ.get("NOTION_API_KEY")
    if token:
        return token

    # Try sourcing from zshrc
    try:
        result = subprocess.run(
            ["zsh", "-c", "source ~/.zshrc && echo ${NOTION_TOKEN:-$NOTION_API_KEY}"],
            capture_output=True, text=True, timeout=5
        )
        token = result.stdout.strip()
        if token:
            return token
    except Exception:
        pass
    return None


def notion_request(endpoint: str, method: str = "GET", data: dict = None) -> dict:
    """Make a request to the Notion API."""
    token = get_notion_token()
    if not token:
        print("Error: NOTION_TOKEN not set. Add to ~/.zshrc:")
        print('  export NOTION_TOKEN="your_token_here"')
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

    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        try:
            error_json = json.loads(error_body)
            print(f"Notion API error {e.code}: {error_json.get('message', error_body)}")
        except json.JSONDecodeError:
            print(f"Notion API error {e.code}: {error_body}")
        sys.exit(1)


def extract_text(rich_text_array: List[dict]) -> str:
    """Extract plain text from rich_text array."""
    if not rich_text_array:
        return ""
    return "".join(t.get("plain_text", "") for t in rich_text_array)


def extract_property_value(prop: dict) -> str:
    """Extract value from a Notion property."""
    prop_type = prop.get("type", "")

    if prop_type == "title":
        return extract_text(prop.get("title", []))
    elif prop_type == "rich_text":
        return extract_text(prop.get("rich_text", []))
    elif prop_type == "number":
        val = prop.get("number")
        return str(val) if val is not None else ""
    elif prop_type == "select":
        sel = prop.get("select")
        return sel.get("name", "") if sel else ""
    elif prop_type == "multi_select":
        items = prop.get("multi_select", [])
        return ", ".join(i.get("name", "") for i in items)
    elif prop_type == "status":
        status = prop.get("status")
        return status.get("name", "") if status else ""
    elif prop_type == "date":
        date = prop.get("date")
        if date:
            start = date.get("start", "")
            end = date.get("end", "")
            return f"{start} → {end}" if end else start
        return ""
    elif prop_type == "checkbox":
        return "✓" if prop.get("checkbox") else "✗"
    elif prop_type == "url":
        return prop.get("url", "")
    elif prop_type == "email":
        return prop.get("email", "")
    elif prop_type == "phone_number":
        return prop.get("phone_number", "")
    elif prop_type == "formula":
        formula = prop.get("formula", {})
        formula_type = formula.get("type", "")
        return str(formula.get(formula_type, ""))
    elif prop_type == "relation":
        relations = prop.get("relation", [])
        return f"[{len(relations)} linked]"
    elif prop_type == "rollup":
        rollup = prop.get("rollup", {})
        rollup_type = rollup.get("type", "")
        if rollup_type == "array":
            return f"[{len(rollup.get('array', []))} items]"
        return str(rollup.get(rollup_type, ""))
    elif prop_type == "people":
        people = prop.get("people", [])
        return ", ".join(p.get("name", p.get("id", "")) for p in people)
    elif prop_type == "files":
        files = prop.get("files", [])
        return ", ".join(f.get("name", "") for f in files)
    elif prop_type == "created_time":
        return prop.get("created_time", "")[:10]
    elif prop_type == "last_edited_time":
        return prop.get("last_edited_time", "")[:10]
    elif prop_type == "created_by":
        user = prop.get("created_by", {})
        return user.get("name", user.get("id", ""))
    elif prop_type == "last_edited_by":
        user = prop.get("last_edited_by", {})
        return user.get("name", user.get("id", ""))
    elif prop_type == "unique_id":
        uid = prop.get("unique_id", {})
        prefix = uid.get("prefix", "")
        number = uid.get("number", "")
        return f"{prefix}-{number}" if prefix else str(number)
    else:
        return f"[{prop_type}]"


def extract_block_text(block: dict) -> str:
    """Extract text content from a block."""
    block_type = block.get("type", "")
    block_data = block.get(block_type, {})

    # Most block types have rich_text
    if "rich_text" in block_data:
        return extract_text(block_data.get("rich_text", []))
    elif "text" in block_data:
        return extract_text(block_data.get("text", []))
    elif block_type == "child_page":
        return f"📄 {block_data.get('title', 'Untitled')}"
    elif block_type == "child_database":
        return f"🗃️ {block_data.get('title', 'Untitled')}"
    elif block_type == "image":
        img = block_data.get("file", block_data.get("external", {}))
        return f"🖼️ [Image: {img.get('url', 'no url')[:50]}...]"
    elif block_type == "file":
        f = block_data.get("file", block_data.get("external", {}))
        return f"📎 [File: {block_data.get('name', f.get('url', '')[:30])}]"
    elif block_type == "bookmark":
        return f"🔗 {block_data.get('url', '')}"
    elif block_type == "equation":
        return f"📐 {block_data.get('expression', '')}"
    elif block_type == "divider":
        return "───────────────────────────────"
    elif block_type == "table_of_contents":
        return "[Table of Contents]"
    elif block_type == "breadcrumb":
        return "[Breadcrumb]"
    elif block_type == "column_list":
        return "[Columns]"
    elif block_type == "column":
        return ""
    elif block_type == "link_preview":
        return f"🔗 {block_data.get('url', '')}"
    elif block_type == "synced_block":
        return "[Synced Block]"
    elif block_type == "template":
        return "[Template]"
    elif block_type == "link_to_page":
        return f"→ [Link to page]"
    elif block_type == "table":
        return f"[Table: {block_data.get('table_width', '?')} columns]"
    elif block_type == "table_row":
        cells = block_data.get("cells", [])
        return " | ".join(extract_text(cell) for cell in cells)
    else:
        return f"[{block_type}]"


def format_block(block: dict, indent: int = 0) -> str:
    """Format a block for display."""
    block_type = block.get("type", "")
    text = extract_block_text(block)
    prefix = "  " * indent

    # Add type-specific prefixes
    type_prefixes = {
        "heading_1": "# ",
        "heading_2": "## ",
        "heading_3": "### ",
        "bulleted_list_item": "• ",
        "numbered_list_item": "1. ",
        "to_do": lambda b: f"[{'x' if b.get('to_do', {}).get('checked') else ' '}] ",
        "toggle": "▶ ",
        "quote": "│ ",
        "callout": lambda b: f"{b.get('callout', {}).get('icon', {}).get('emoji', '💡')} ",
        "code": "```",
    }

    type_prefix = type_prefixes.get(block_type, "")
    if callable(type_prefix):
        type_prefix = type_prefix(block)

    if block_type == "code":
        lang = block.get("code", {}).get("language", "")
        return f"{prefix}```{lang}\n{prefix}{text}\n{prefix}```"

    return f"{prefix}{type_prefix}{text}"


# === Commands ===

def cmd_search(query: str, filter_type: str = None, limit: int = 20):
    """Search for pages and databases."""
    data = {
        "query": query,
        "page_size": limit
    }

    if filter_type in ("page", "database"):
        data["filter"] = {"property": "object", "value": filter_type}

    result = notion_request("search", method="POST", data=data)
    results = result.get("results", [])

    if not results:
        print(f"No results found for '{query}'")
        return

    print(f"Found {len(results)} result(s) for '{query}':\n")

    for item in results:
        obj_type = item.get("object", "")
        item_id = item.get("id", "")

        if obj_type == "page":
            props = item.get("properties", {})
            # Try to find title
            title = ""
            for prop_name, prop_val in props.items():
                if prop_val.get("type") == "title":
                    title = extract_property_value(prop_val)
                    break
            if not title:
                title = "Untitled"

            parent = item.get("parent", {})
            parent_type = parent.get("type", "")

            icon = item.get("icon", {})
            emoji = icon.get("emoji", "📄") if icon and icon.get("type") == "emoji" else "📄"

            print(f"{emoji} {title}")
            print(f"   ID: {item_id}")
            print(f"   Parent: {parent_type}")
            print()

        elif obj_type == "database":
            title_arr = item.get("title", [])
            title = extract_text(title_arr) or "Untitled Database"

            desc_arr = item.get("description", [])
            desc = extract_text(desc_arr)

            icon = item.get("icon", {})
            emoji = icon.get("emoji", "🗃️") if icon and icon.get("type") == "emoji" else "🗃️"

            print(f"{emoji} {title}")
            print(f"   ID: {item_id}")
            if desc:
                print(f"   Description: {desc[:60]}...")
            print()


def cmd_page(page_id: str):
    """Show page properties."""
    result = notion_request(f"pages/{page_id}")

    props = result.get("properties", {})
    parent = result.get("parent", {})
    icon = result.get("icon", {})
    cover = result.get("cover", {})

    # Find title
    title = "Untitled"
    for prop_name, prop_val in props.items():
        if prop_val.get("type") == "title":
            title = extract_property_value(prop_val)
            break

    emoji = icon.get("emoji", "") if icon and icon.get("type") == "emoji" else ""

    print(f"\n{'='*60}")
    print(f"{emoji} {title}" if emoji else title)
    print(f"{'='*60}")
    print(f"ID: {result.get('id', '')}")
    print(f"Created: {result.get('created_time', '')[:10]}")
    print(f"Edited:  {result.get('last_edited_time', '')[:10]}")
    print(f"Parent:  {parent.get('type', '')} - {parent.get(parent.get('type', '') + '_id', parent.get('page_id', parent.get('database_id', '')))[:20]}")

    if cover:
        cover_type = cover.get("type", "")
        cover_url = cover.get(cover_type, {}).get("url", "")
        print(f"Cover:   {cover_url[:50]}...")

    print(f"\n--- Properties ---")
    for prop_name, prop_val in sorted(props.items()):
        value = extract_property_value(prop_val)
        if value:
            prop_type = prop_val.get("type", "")
            print(f"{prop_name} ({prop_type}): {value[:80]}")


def cmd_read(page_id: str, max_depth: int = 3):
    """Read page content (blocks)."""
    def fetch_blocks(block_id: str, depth: int = 0):
        if depth > max_depth:
            return

        result = notion_request(f"blocks/{block_id}/children?page_size=100")
        blocks = result.get("results", [])

        for block in blocks:
            line = format_block(block, indent=depth)
            if line.strip():
                print(line)

            # Fetch children if has_children
            if block.get("has_children"):
                fetch_blocks(block.get("id"), depth + 1)

    # First get page info for title
    try:
        page = notion_request(f"pages/{page_id}")
        props = page.get("properties", {})
        title = "Untitled"
        for prop_name, prop_val in props.items():
            if prop_val.get("type") == "title":
                title = extract_property_value(prop_val)
                break

        icon = page.get("icon", {})
        emoji = icon.get("emoji", "") if icon and icon.get("type") == "emoji" else ""

        print(f"\n{'='*60}")
        print(f"{emoji} {title}" if emoji else title)
        print(f"{'='*60}\n")
    except Exception:
        print(f"\n--- Content of {page_id} ---\n")

    fetch_blocks(page_id)


def cmd_databases(limit: int = 50):
    """List all accessible databases."""
    data = {
        "filter": {"property": "object", "value": "database"},
        "page_size": limit
    }

    result = notion_request("search", method="POST", data=data)
    databases = result.get("results", [])

    if not databases:
        print("No databases found")
        return

    print(f"Found {len(databases)} database(s):\n")
    print(f"{'Title':<40} {'ID':<36}")
    print("-" * 78)

    for db in databases:
        title_arr = db.get("title", [])
        title = extract_text(title_arr) or "Untitled"

        icon = db.get("icon", {})
        emoji = icon.get("emoji", "🗃️") if icon and icon.get("type") == "emoji" else "🗃️"

        db_id = db.get("id", "")
        title_display = f"{emoji} {title}"[:39]

        print(f"{title_display:<40} {db_id}")


def cmd_db_schema(database_id: str):
    """Show database schema."""
    result = notion_request(f"databases/{database_id}")

    title_arr = result.get("title", [])
    title = extract_text(title_arr) or "Untitled Database"

    desc_arr = result.get("description", [])
    desc = extract_text(desc_arr)

    props = result.get("properties", {})

    icon = result.get("icon", {})
    emoji = icon.get("emoji", "🗃️") if icon and icon.get("type") == "emoji" else "🗃️"

    print(f"\n{'='*60}")
    print(f"{emoji} {title}")
    print(f"{'='*60}")
    print(f"ID: {result.get('id', '')}")
    if desc:
        print(f"Description: {desc}")

    print(f"\n--- Schema ({len(props)} properties) ---\n")
    print(f"{'Property':<25} {'Type':<20} {'Details'}")
    print("-" * 70)

    for prop_name, prop_schema in sorted(props.items()):
        prop_type = prop_schema.get("type", "")
        details = ""

        if prop_type == "select":
            options = prop_schema.get("select", {}).get("options", [])
            details = ", ".join(o.get("name", "") for o in options[:5])
            if len(options) > 5:
                details += f" (+{len(options)-5} more)"
        elif prop_type == "multi_select":
            options = prop_schema.get("multi_select", {}).get("options", [])
            details = ", ".join(o.get("name", "") for o in options[:5])
            if len(options) > 5:
                details += f" (+{len(options)-5} more)"
        elif prop_type == "status":
            options = prop_schema.get("status", {}).get("options", [])
            details = ", ".join(o.get("name", "") for o in options)
        elif prop_type == "relation":
            rel = prop_schema.get("relation", {})
            details = f"→ {rel.get('database_id', '')[:12]}..."
        elif prop_type == "formula":
            details = prop_schema.get("formula", {}).get("expression", "")[:30]
        elif prop_type == "rollup":
            rollup = prop_schema.get("rollup", {})
            details = f"{rollup.get('function', '')} of {rollup.get('relation_property_name', '')}"

        print(f"{prop_name:<25} {prop_type:<20} {details[:30]}")


def cmd_query(database_id: str, filter_json: str = None, sort_prop: str = None,
              sort_dir: str = "ascending", limit: int = 50):
    """Query a database."""
    data = {"page_size": limit}

    if filter_json:
        try:
            data["filter"] = json.loads(filter_json)
        except json.JSONDecodeError as e:
            print(f"Invalid filter JSON: {e}")
            sys.exit(1)

    if sort_prop:
        data["sorts"] = [{"property": sort_prop, "direction": sort_dir}]

    result = notion_request(f"databases/{database_id}/query", method="POST", data=data)
    pages = result.get("results", [])

    if not pages:
        print("No results found")
        return

    # Get property names from first page
    if pages:
        all_props = list(pages[0].get("properties", {}).keys())
        # Prioritize title property
        title_prop = None
        for p in all_props:
            if pages[0]["properties"][p].get("type") == "title":
                title_prop = p
                break

        # Show first few properties
        display_props = []
        if title_prop:
            display_props.append(title_prop)
        for p in all_props:
            if p != title_prop and len(display_props) < 5:
                display_props.append(p)

    print(f"Found {len(pages)} result(s):\n")

    # Header
    header = " | ".join(f"{p[:15]:<15}" for p in display_props)
    print(header)
    print("-" * len(header))

    # Rows
    for page in pages:
        props = page.get("properties", {})
        row_vals = []
        for prop_name in display_props:
            val = extract_property_value(props.get(prop_name, {}))
            row_vals.append(f"{val[:15]:<15}")
        print(" | ".join(row_vals))

    if result.get("has_more"):
        print(f"\n... more results available (use --limit to see more)")


def cmd_block(block_id: str):
    """Read a specific block and its children."""
    result = notion_request(f"blocks/{block_id}")

    print(f"\n--- Block: {block_id} ---")
    print(f"Type: {result.get('type', '')}")
    print(f"Has children: {result.get('has_children', False)}")
    print(f"\nContent:")
    print(format_block(result))

    if result.get("has_children"):
        print(f"\n--- Children ---")
        children = notion_request(f"blocks/{block_id}/children?page_size=100")
        for child in children.get("results", []):
            print(format_block(child, indent=1))


def extract_files_from_property(prop: dict) -> List[Dict[str, str]]:
    """Extract file URLs from a files property."""
    files = []
    if prop.get("type") != "files":
        return files

    for f in prop.get("files", []):
        file_info = {"name": f.get("name", "unnamed")}

        # Handle both internal and external files
        if f.get("type") == "file":
            file_info["url"] = f.get("file", {}).get("url", "")
            file_info["expiry"] = f.get("file", {}).get("expiry_time", "")
        elif f.get("type") == "external":
            file_info["url"] = f.get("external", {}).get("url", "")

        if file_info.get("url"):
            files.append(file_info)

    return files


def download_file(url: str, output_path: str) -> bool:
    """Download a file from URL to output path."""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=60) as response:
            with open(output_path, 'wb') as f:
                f.write(response.read())
        return True
    except Exception as e:
        print(f"Error downloading: {e}", file=sys.stderr)
        return False


def cmd_download(page_id: str, output_dir: str = "."):
    """Download all files from a page's properties."""
    result = notion_request(f"pages/{page_id}")
    props = result.get("properties", {})

    # Find title for display
    title = "Untitled"
    for prop_name, prop_val in props.items():
        if prop_val.get("type") == "title":
            title = extract_property_value(prop_val)
            break

    print(f"Scanning page: {title}")

    # Find all file properties
    all_files = []
    for prop_name, prop_val in props.items():
        if prop_val.get("type") == "files":
            files = extract_files_from_property(prop_val)
            for f in files:
                f["property"] = prop_name
            all_files.extend(files)

    if not all_files:
        print("No files found in page properties")
        return

    print(f"Found {len(all_files)} file(s):\n")

    # Create output directory
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Download each file
    for f in all_files:
        filename = f["name"]
        url = f["url"]
        prop_name = f.get("property", "")

        output_file = out_path / filename
        print(f"  [{prop_name}] {filename}...", end=" ", flush=True)

        if download_file(url, str(output_file)):
            print(f"OK ({output_file})")
        else:
            print("FAILED")


def cmd_files(database_id: str, entry_name: str, output_dir: str = ".",
              file_property: str = None):
    """Download files from a database entry by name."""
    # Query database for the entry
    data = {
        "page_size": 10,
    }

    result = notion_request(f"databases/{database_id}/query", method="POST", data=data)
    pages = result.get("results", [])

    # Find entry by name (match against title property)
    target_page = None
    for page in pages:
        props = page.get("properties", {})
        for prop_name, prop_val in props.items():
            if prop_val.get("type") == "title":
                title = extract_property_value(prop_val)
                if title.lower() == entry_name.lower():
                    target_page = page
                    break
        if target_page:
            break

    # If not found in first 10, search more specifically
    if not target_page:
        # Try fetching more results
        data["page_size"] = 100
        result = notion_request(f"databases/{database_id}/query", method="POST", data=data)
        pages = result.get("results", [])

        for page in pages:
            props = page.get("properties", {})
            for prop_name, prop_val in props.items():
                if prop_val.get("type") == "title":
                    title = extract_property_value(prop_val)
                    if title.lower() == entry_name.lower():
                        target_page = page
                        break
            if target_page:
                break

    if not target_page:
        print(f"Entry '{entry_name}' not found in database")
        # Show available entries
        print("\nAvailable entries:")
        for page in pages[:10]:
            props = page.get("properties", {})
            for prop_name, prop_val in props.items():
                if prop_val.get("type") == "title":
                    title = extract_property_value(prop_val)
                    print(f"  - {title}")
                    break
        return

    # Extract files
    props = target_page.get("properties", {})
    all_files = []

    for prop_name, prop_val in props.items():
        if prop_val.get("type") == "files":
            # If specific property requested, only use that one
            if file_property and prop_name.lower() != file_property.lower():
                continue
            files = extract_files_from_property(prop_val)
            for f in files:
                f["property"] = prop_name
            all_files.extend(files)

    if not all_files:
        print(f"No files found in '{entry_name}'")
        # Show file properties available
        file_props = [p for p, v in props.items() if v.get("type") == "files"]
        if file_props:
            print(f"File properties: {', '.join(file_props)}")
        return

    print(f"Found {len(all_files)} file(s) in '{entry_name}':\n")

    # Create output directory
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Download each file
    for f in all_files:
        filename = f["name"]
        url = f["url"]
        prop_name = f.get("property", "")

        output_file = out_path / filename
        print(f"  [{prop_name}] {filename}...", end=" ", flush=True)

        if download_file(url, str(output_file)):
            print(f"OK ({output_file})")
        else:
            print("FAILED")


def main():
    parser = argparse.ArgumentParser(
        description="Notion CLI - Read and search Notion pages and databases",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  notion_cli.py search "meeting notes"
  notion_cli.py search "project" --type page
  notion_cli.py databases
  notion_cli.py db a993dc2d-9ece-4be1-bb39-ef9dbcecdea6
  notion_cli.py page 12345678-1234-1234-1234-123456789abc
  notion_cli.py read 12345678-1234-1234-1234-123456789abc
  notion_cli.py query DATABASE_ID --filter '{"property": "Status", "select": {"equals": "Done"}}'
  notion_cli.py download PAGE_ID -o ./downloads
  notion_cli.py files YOUR_DATABASE_ID "438-C" -o ./vectors
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Search command
    search_parser = subparsers.add_parser('search', help='Search pages and databases')
    search_parser.add_argument('query', help='Search query')
    search_parser.add_argument('--type', '-t', choices=['page', 'database'],
                               help='Filter by type')
    search_parser.add_argument('--limit', '-l', type=int, default=20,
                               help='Max results (default: 20)')

    # Page command
    page_parser = subparsers.add_parser('page', help='Show page properties')
    page_parser.add_argument('page_id', help='Page ID')

    # Read command
    read_parser = subparsers.add_parser('read', help='Read page content')
    read_parser.add_argument('page_id', help='Page ID')
    read_parser.add_argument('--depth', '-d', type=int, default=3,
                             help='Max depth for nested blocks (default: 3)')

    # Databases command
    db_list_parser = subparsers.add_parser('databases', help='List all databases')
    db_list_parser.add_argument('--limit', '-l', type=int, default=50,
                                help='Max results (default: 50)')

    # DB schema command
    db_parser = subparsers.add_parser('db', help='Show database schema')
    db_parser.add_argument('database_id', help='Database ID')

    # Query command
    query_parser = subparsers.add_parser('query', help='Query a database')
    query_parser.add_argument('database_id', help='Database ID')
    query_parser.add_argument('--filter', '-f', help='Filter as JSON')
    query_parser.add_argument('--sort', '-s', help='Property to sort by')
    query_parser.add_argument('--dir', choices=['ascending', 'descending'],
                              default='ascending', help='Sort direction')
    query_parser.add_argument('--limit', '-l', type=int, default=50,
                              help='Max results (default: 50)')

    # Block command
    block_parser = subparsers.add_parser('block', help='Read a specific block')
    block_parser.add_argument('block_id', help='Block ID')

    # Download command
    download_parser = subparsers.add_parser('download', help='Download files from a page')
    download_parser.add_argument('page_id', help='Page ID')
    download_parser.add_argument('--output', '-o', default='.', help='Output directory (default: .)')

    # Files command (download by name from database)
    files_parser = subparsers.add_parser('files', help='Download files from database entry by name')
    files_parser.add_argument('database_id', help='Database ID')
    files_parser.add_argument('name', help='Entry name to download files from')
    files_parser.add_argument('--output', '-o', default='.', help='Output directory (default: .)')
    files_parser.add_argument('--property', '-p', help='Specific file property to download')

    args = parser.parse_args()

    if args.command == 'search':
        cmd_search(args.query, args.type, args.limit)
    elif args.command == 'page':
        cmd_page(args.page_id)
    elif args.command == 'read':
        cmd_read(args.page_id, args.depth)
    elif args.command == 'databases':
        cmd_databases(args.limit)
    elif args.command == 'db':
        cmd_db_schema(args.database_id)
    elif args.command == 'query':
        cmd_query(args.database_id, args.filter, args.sort, args.dir, args.limit)
    elif args.command == 'block':
        cmd_block(args.block_id)
    elif args.command == 'download':
        cmd_download(args.page_id, args.output)
    elif args.command == 'files':
        cmd_files(args.database_id, args.name, args.output, args.property)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
