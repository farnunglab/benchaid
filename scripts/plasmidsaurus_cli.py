#!/usr/bin/env python3
"""
Plasmidsaurus CLI - Fetch sequencing data from Plasmidsaurus API

Setup:
    1. Generate credentials at https://www.plasmidsaurus.com/user-info
    2. Export environment variables:
        export PLASMIDSAURUS_CLIENT_ID="your_client_id"
        export PLASMIDSAURUS_CLIENT_SECRET="your_client_secret"

Usage:
    plasmidsaurus_cli.py list                    # List all items
    plasmidsaurus_cli.py info <item_code>        # Show item details
    plasmidsaurus_cli.py download <item_code>    # Download results for an item
    plasmidsaurus_cli.py auto-fetch              # Auto-download new results
"""

import os
import sys
import argparse
import zipfile
from pathlib import Path
from datetime import datetime, timezone

try:
    import requests
    from requests.auth import HTTPBasicAuth
except ImportError:
    print("Error: 'requests' package is required. Install with: pip install requests")
    sys.exit(1)

API_URL = "https://plasmidsaurus.com"
DEFAULT_DATA_DIR = "./plasmidsaurus_data"


def get_credentials():
    """Get API credentials from environment variables."""
    client_id = os.getenv("PLASMIDSAURUS_CLIENT_ID")
    client_secret = os.getenv("PLASMIDSAURUS_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("Error: Missing credentials. Set environment variables:")
        print("  export PLASMIDSAURUS_CLIENT_ID='your_client_id'")
        print("  export PLASMIDSAURUS_CLIENT_SECRET='your_client_secret'")
        print("\nGenerate credentials at: https://www.plasmidsaurus.com/user-info")
        sys.exit(1)

    return client_id, client_secret


def get_access_token(client_id: str, client_secret: str) -> str:
    """Obtain OAuth2 access token using client credentials flow."""
    payload = {"grant_type": "client_credentials", "scope": "item:read"}
    res = requests.post(
        f"{API_URL}/oauth/token",
        data=payload,
        auth=HTTPBasicAuth(client_id, client_secret),
    )
    res.raise_for_status()
    return res.json()["access_token"]


def download_file(url: str, output_file: str, quiet: bool = False):
    """Download a file with progress indicator."""
    response = requests.get(url, stream=True)
    response.raise_for_status()

    total_size = int(response.headers.get("content-length", 0))
    block_size = 1024
    downloaded = 0
    progress_bar_size = 40

    with open(output_file, "wb") as file:
        for data in response.iter_content(chunk_size=block_size):
            size = file.write(data)
            downloaded += size
            if not quiet and total_size > 0:
                done = int(progress_bar_size * downloaded / total_size)
                sys.stdout.write(
                    f"\r  [{'=' * done}{' ' * (progress_bar_size-done)}] {downloaded:,}/{total_size:,} bytes"
                )
                sys.stdout.flush()

    if not quiet:
        print(f"\n  Downloaded: {output_file}")


def unzip_file(zip_file: str, output_dir: str, quiet: bool = False):
    """Extract zip archive to directory."""
    if not quiet:
        print(f"  Extracting to: {output_dir}")
    with zipfile.ZipFile(zip_file, "r") as zip_ref:
        zip_ref.extractall(output_dir)


def get_items(access_token: str, include_shared: bool = True) -> list:
    """Retrieve all items from the API."""
    headers = {"Authorization": f"Bearer {access_token}"}

    res = requests.get(f"{API_URL}/api/items", headers=headers)
    res.raise_for_status()
    items = res.json()

    if include_shared:
        res = requests.get(f"{API_URL}/api/items?shared=true", headers=headers)
        res.raise_for_status()
        shared_items = res.json()
        items.extend(shared_items)

    return items


def get_item_info(item_code: str, access_token: str) -> dict:
    """Get detailed information about a specific item."""
    res = requests.get(
        f"{API_URL}/api/item/{item_code}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    res.raise_for_status()
    return res.json()


def download_results(item_code: str, access_token: str, destination_dir: str,
                     quiet: bool = False, keep_zip: bool = False):
    """Download results and reads for an item."""
    headers = {"Authorization": f"Bearer {access_token}"}
    os.makedirs(destination_dir, exist_ok=True)

    # Download results
    if not quiet:
        print(f"\nDownloading results for {item_code}...")

    res = requests.get(f"{API_URL}/api/item/{item_code}/results", headers=headers)
    if res.ok:
        data = res.json()
        if "link" in data:
            filename = Path(destination_dir) / f"{item_code}_results.zip"
            download_file(data["link"], str(filename), quiet)
            unzip_file(str(filename), str(Path(destination_dir) / "results"), quiet)
            if not keep_zip:
                os.remove(filename)
    else:
        if not quiet:
            print(f"  No results available for {item_code}")

    # Download reads
    if not quiet:
        print(f"\nDownloading reads for {item_code}...")

    res = requests.get(f"{API_URL}/api/item/{item_code}/reads", headers=headers)
    if res.ok:
        data = res.json()
        if "link" in data:
            filename = Path(destination_dir) / f"{item_code}_reads.zip"
            download_file(data["link"], str(filename), quiet)
            unzip_file(str(filename), str(Path(destination_dir) / "reads"), quiet)
            if not keep_zip:
                os.remove(filename)
    else:
        if not quiet:
            print(f"  No reads available for {item_code}")


def cmd_list(args):
    """List all items."""
    client_id, client_secret = get_credentials()
    access_token = get_access_token(client_id, client_secret)

    items = get_items(access_token, include_shared=not args.no_shared)

    if not items:
        print("No items found.")
        return

    # Filter by status if specified
    if args.status:
        items = [i for i in items if i.get("status") == args.status]

    # Sort by date (most recent first)
    items.sort(key=lambda x: x.get("done_date") or x.get("created_date") or "", reverse=True)

    if args.json:
        import json
        print(json.dumps(items, indent=2))
        return

    # Print table header
    print(f"\n{'Code':<12} {'Status':<12} {'Name':<30} {'Done Date':<20}")
    print("-" * 76)

    for item in items:
        code = item.get("code", "N/A")
        status = item.get("status", "N/A")
        name = item.get("name", "")[:28] or "N/A"
        done_date = item.get("done_date", "")[:19] if item.get("done_date") else "Pending"

        # Color code status
        if status == "complete":
            status_display = f"\033[92m{status}\033[0m"  # Green
        elif status == "processing":
            status_display = f"\033[93m{status}\033[0m"  # Yellow
        else:
            status_display = status

        print(f"{code:<12} {status_display:<21} {name:<30} {done_date:<20}")

    print(f"\nTotal: {len(items)} items")


def cmd_info(args):
    """Show detailed item information."""
    client_id, client_secret = get_credentials()
    access_token = get_access_token(client_id, client_secret)

    try:
        info = get_item_info(args.item_code, access_token)
    except requests.HTTPError as e:
        print(f"Error: Could not find item '{args.item_code}'")
        sys.exit(1)

    if args.json:
        import json
        print(json.dumps(info, indent=2))
        return

    print(f"\n{'='*50}")
    print(f"Item: {info.get('code', 'N/A')}")
    print(f"{'='*50}")
    print(f"Name:        {info.get('name', 'N/A')}")
    print(f"Status:      {info.get('status', 'N/A')}")
    print(f"Created:     {info.get('created_date', 'N/A')}")
    print(f"Completed:   {info.get('done_date', 'N/A')}")

    if info.get("samples"):
        print(f"\nSamples ({len(info['samples'])}):")
        for sample in info["samples"]:
            print(f"  - {sample.get('name', 'N/A')}: {sample.get('status', 'N/A')}")


def cmd_download(args):
    """Download results for an item."""
    client_id, client_secret = get_credentials()
    access_token = get_access_token(client_id, client_secret)

    # Verify item exists
    try:
        info = get_item_info(args.item_code, access_token)
        print(f"Item: {args.item_code} - {info.get('name', 'N/A')}")
        print(f"Status: {info.get('status', 'N/A')}")
    except requests.HTTPError:
        print(f"Error: Could not find item '{args.item_code}'")
        sys.exit(1)

    dest_dir = Path(args.output) / args.item_code
    download_results(args.item_code, access_token, str(dest_dir),
                     quiet=args.quiet, keep_zip=args.keep_zip)

    print(f"\nResults saved to: {dest_dir}")


def cmd_auto_fetch(args):
    """Automatically download new completed results."""
    client_id, client_secret = get_credentials()
    access_token = get_access_token(client_id, client_secret)

    data_dir = Path(args.output)
    data_dir.mkdir(parents=True, exist_ok=True)

    # Get all items
    items = get_items(access_token)

    # Filter for completed items
    items = [i for i in items if i.get("status") == "complete"]

    # Filter by date if specified
    if args.after:
        try:
            after_date = datetime.fromisoformat(args.after.replace("Z", "+00:00"))
            if after_date.tzinfo is None:
                after_date = after_date.replace(tzinfo=timezone.utc)
            items = [
                i for i in items
                if i.get("done_date") and
                datetime.fromisoformat(i["done_date"].replace("Z", "+00:00")) > after_date
            ]
        except ValueError:
            print(f"Error: Invalid date format '{args.after}'. Use ISO format (YYYY-MM-DD)")
            sys.exit(1)

    # Find items not yet downloaded
    existing = set()
    if data_dir.exists():
        existing = {d.name for d in data_dir.iterdir() if d.is_dir()}

    to_download = [i for i in items if i.get("code") not in existing]

    # Limit downloads per run
    if args.limit:
        to_download = to_download[:args.limit]

    if not to_download:
        print("No new items to download.")
        return

    print(f"Found {len(to_download)} new items to download:")
    for item in to_download:
        print(f"  - {item.get('code')}: {item.get('name', 'N/A')}")

    print()

    for item in to_download:
        code = item.get("code")
        item_dir = data_dir / code
        item_dir.mkdir(exist_ok=True)

        try:
            download_results(code, access_token, str(item_dir),
                           quiet=args.quiet, keep_zip=args.keep_zip)
            print(f"Downloaded: {code}\n")
        except Exception as e:
            print(f"Error downloading {code}: {e}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Plasmidsaurus CLI - Fetch sequencing data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list                          List all items
  %(prog)s list --status complete        List only completed items
  %(prog)s info ABC123                   Show details for item ABC123
  %(prog)s download ABC123               Download results for ABC123
  %(prog)s auto-fetch                    Auto-download new results
  %(prog)s auto-fetch --after 2024-01-01 Download results after date

Environment Variables:
  PLASMIDSAURUS_CLIENT_ID      Your API client ID
  PLASMIDSAURUS_CLIENT_SECRET  Your API client secret

Get credentials at: https://www.plasmidsaurus.com/user-info
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # List command
    list_parser = subparsers.add_parser("list", help="List all items")
    list_parser.add_argument("--status", choices=["complete", "processing", "pending"],
                            help="Filter by status")
    list_parser.add_argument("--no-shared", action="store_true",
                            help="Exclude shared items")
    list_parser.add_argument("--json", action="store_true",
                            help="Output as JSON")
    list_parser.set_defaults(func=cmd_list)

    # Info command
    info_parser = subparsers.add_parser("info", help="Show item details")
    info_parser.add_argument("item_code", help="Item code to look up")
    info_parser.add_argument("--json", action="store_true",
                            help="Output as JSON")
    info_parser.set_defaults(func=cmd_info)

    # Download command
    dl_parser = subparsers.add_parser("download", help="Download results for an item")
    dl_parser.add_argument("item_code", help="Item code to download")
    dl_parser.add_argument("-o", "--output", default=DEFAULT_DATA_DIR,
                          help=f"Output directory (default: {DEFAULT_DATA_DIR})")
    dl_parser.add_argument("-q", "--quiet", action="store_true",
                          help="Suppress progress output")
    dl_parser.add_argument("--keep-zip", action="store_true",
                          help="Keep zip files after extraction")
    dl_parser.set_defaults(func=cmd_download)

    # Auto-fetch command
    auto_parser = subparsers.add_parser("auto-fetch",
                                        help="Automatically download new results")
    auto_parser.add_argument("-o", "--output", default=DEFAULT_DATA_DIR,
                            help=f"Output directory (default: {DEFAULT_DATA_DIR})")
    auto_parser.add_argument("--after", metavar="DATE",
                            help="Only download items completed after date (YYYY-MM-DD)")
    auto_parser.add_argument("--limit", type=int, default=5,
                            help="Max items to download per run (default: 5)")
    auto_parser.add_argument("-q", "--quiet", action="store_true",
                            help="Suppress progress output")
    auto_parser.add_argument("--keep-zip", action="store_true",
                            help="Keep zip files after extraction")
    auto_parser.set_defaults(func=cmd_auto_fetch)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
