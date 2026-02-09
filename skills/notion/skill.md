---
name: notion
description: Search, read, and download from Notion. Use when the user asks about protocols, lab databases, or needs to download files (like vector maps) from Notion.
---

# Notion CLI

Search, read, query, and download files from Notion pages and databases.

## CLI Location
```
scripts/notion_cli.py
```

## Environment
```bash
export NOTION_TOKEN="your_token_here"
```

## Commands

### Search
```bash
python3 scripts/notion_cli.py search "query"
python3 scripts/notion_cli.py search "protocol" --type page
python3 scripts/notion_cli.py search "proteins" --type database
```

### Read Page Content
```bash
python3 scripts/notion_cli.py read <page_id> --depth 3
```

### List Databases
```bash
python3 scripts/notion_cli.py databases
```

### Query Database
```bash
python3 scripts/notion_cli.py query <database_id>
python3 scripts/notion_cli.py query <database_id> --filter '{"property": "Status", "select": {"equals": "Done"}}'
```

### Download Files from Page
```bash
python3 scripts/notion_cli.py download <page_id> -o ./output
```

### Download Files by Entry Name
```bash
# Download vector file from Series-438 database
python3 scripts/notion_cli.py files <YOUR_SERIES_438_DB_ID> "438-C" -o ./vectors

# Download from specific property
python3 scripts/notion_cli.py files <database_id> "entry name" -o ./output --property "Plasmid maps"
```

## Key Database IDs

Configure your Notion database IDs in `.env` or note them here:

| Database | ID | Contents |
|----------|-----|----------|
| Series-438 | `<YOUR_DB_ID>` | 438 vector series (.dna files) |
| Lab Meeting Schedule | `<YOUR_DB_ID>` | Meeting dates/presenters |
| Protein purifications | `<YOUR_DB_ID>` | Active purifications |

## Example: Download and Parse Vector

```bash
# 1. Download 438-C vector from Notion
python3 scripts/notion_cli.py files <YOUR_SERIES_438_DB_ID> "438-C" -o ./vectors

# 2. Parse with SnapGene reader
python3 scripts/snapgene_cli.py ./vectors/438-C.dna --features

# 3. Convert to GenBank
python3 scripts/snapgene_cli.py ./vectors/438-C.dna --export-gb ./vectors/438-C.gb
```

## Output Formats

- Search results: page/database listings with IDs
- Page content: formatted blocks (headings, lists, code)
- Query results: table format with key properties
- File downloads: saved to specified directory
