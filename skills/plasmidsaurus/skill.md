---
name: plasmidsaurus
description: Fetch sequencing data from Plasmidsaurus. Use when the user asks about listing sequencing orders, downloading sequencing results, checking order status, or retrieving plasmid sequences from Plasmidsaurus.
allowed-tools: Bash(plasmidsaurus_cli:*), Bash(python3:*)
---

# Plasmidsaurus CLI

Fetch sequencing data from the Plasmidsaurus API.

## Prerequisites

Requires environment variables (already configured in ~/.zshrc):
- `PLASMIDSAURUS_CLIENT_ID`
- `PLASMIDSAURUS_CLIENT_SECRET`

Always source ~/.zshrc before running commands:
```bash
source ~/.zshrc && python3 scripts/plasmidsaurus_cli.py <command>
```

## Commands

### List Orders
List all sequencing orders:
```bash
source ~/.zshrc && python3 scripts/plasmidsaurus_cli.py list
```

Options:
- `--status {complete,processing,pending}`: Filter by status
- `--no-shared`: Exclude shared items
- `--json`: Output as JSON

### Item Info
Get detailed information about a specific order:
```bash
source ~/.zshrc && python3 scripts/plasmidsaurus_cli.py info <item_code>
```

Options:
- `--json`: Output as JSON

### Download Results
Download sequencing results and reads for a specific order:
```bash
source ~/.zshrc && python3 scripts/plasmidsaurus_cli.py download <item_code>
```

Options:
- `-o, --output DIR`: Output directory (default: ./plasmidsaurus_data)
- `-q, --quiet`: Suppress progress output
- `--keep-zip`: Keep zip files after extraction

Downloads are saved to `<output_dir>/<item_code>/` with subdirectories:
- `results/`: Assembled sequences, annotations, maps
- `reads/`: Raw sequencing reads

### Auto-Fetch New Results
Automatically download all new completed results:
```bash
source ~/.zshrc && python3 scripts/plasmidsaurus_cli.py auto-fetch
```

Options:
- `-o, --output DIR`: Output directory (default: ./plasmidsaurus_data)
- `--after DATE`: Only download items completed after date (YYYY-MM-DD)
- `--limit N`: Max items to download per run (default: 5)
- `-q, --quiet`: Suppress progress output
- `--keep-zip`: Keep zip files after extraction

## Examples

```bash
# List all completed orders
source ~/.zshrc && python3 scripts/plasmidsaurus_cli.py list --status complete

# Get info for a specific order
source ~/.zshrc && python3 scripts/plasmidsaurus_cli.py info 8WGZXW

# Download results for an order
source ~/.zshrc && python3 scripts/plasmidsaurus_cli.py download 8WGZXW -o ./seq_data

# Auto-fetch results from the last month
source ~/.zshrc && python3 scripts/plasmidsaurus_cli.py auto-fetch --after 2025-01-01
```
