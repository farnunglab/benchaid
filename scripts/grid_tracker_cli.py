#!/usr/bin/env python3
"""
Grid Tracker CLI - Track cryo-EM grid preparation and storage

Usage:
    grid_tracker_cli.py add --sample <name> [options]     Add a new grid
    grid_tracker_cli.py list [--sample <name>] [--status] List grids
    grid_tracker_cli.py info <grid_id>                    Show grid details
    grid_tracker_cli.py find <query>                      Search grids
    grid_tracker_cli.py clip <grid_id>                    Mark grid as clipped
    grid_tracker_cli.py unclip <grid_id>                  Mark grid as not clipped
    grid_tracker_cli.py screen <grid_id> [--notes]        Log screening results
    grid_tracker_cli.py update <grid_id> [--field value]  Update grid fields
    grid_tracker_cli.py delete <grid_id>                  Delete a grid
    grid_tracker_cli.py stats                             Show statistics
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

# Database location
DB_PATH = Path(__file__).parent / "grids.db"

# Grid type presets
GRID_TYPES = [
    "Quantifoil R1.2/1.3 Cu 300",
    "Quantifoil R1.2/1.3 Au 300",
    "Quantifoil R2/2 Cu 300",
    "Quantifoil R2/1 Cu 300",
    "C-flat 1.2/1.3 Cu 300",
    "C-flat 2/2 Cu 300",
    "UltrAuFoil R1.2/1.3 Au 300",
    "UltrAuFoil R2/2 Au 300",
]

# Status options
GRID_STATUSES = ["available", "screening", "collected", "used", "discarded"]


# =============================================================================
# Database Functions
# =============================================================================

def get_connection() -> sqlite3.Connection:
    """Get database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialize database schema."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS grids (
            id TEXT PRIMARY KEY,
            sample_name TEXT NOT NULL,
            concentration_nm REAL,
            grid_type TEXT,
            glow_discharge_sec REAL,
            glow_discharge_ma REAL,
            blot_time_sec REAL,
            blot_force INTEGER,
            humidity_pct REAL,
            temperature_c REAL,
            plunge_date TEXT,
            prepared_by TEXT,
            ice_quality_notes TEXT,
            clipped INTEGER DEFAULT 0,
            rack_location TEXT,
            puck_location TEXT,
            box_id TEXT,
            box_position INTEGER,
            screened INTEGER DEFAULT 0,
            screening_notes TEXT,
            dataset_id TEXT,
            status TEXT DEFAULT 'available',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create indexes for common queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_grids_sample ON grids(sample_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_grids_status ON grids(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_grids_clipped ON grids(clipped)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_grids_rack ON grids(rack_location)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_grids_puck ON grids(puck_location)")

    conn.commit()
    conn.close()


def generate_grid_id(sample_name: str) -> str:
    """Generate a unique grid ID based on sample name and timestamp."""
    # Clean sample name
    clean_name = "".join(c if c.isalnum() else "_" for c in sample_name)[:20]
    timestamp = datetime.now().strftime("%y%m%d_%H%M%S")
    return f"G_{clean_name}_{timestamp}"


# =============================================================================
# Grid Operations
# =============================================================================

def add_grid(
    sample_name: str,
    concentration_nm: Optional[float] = None,
    grid_type: Optional[str] = None,
    glow_discharge_sec: Optional[float] = None,
    glow_discharge_ma: Optional[float] = None,
    blot_time_sec: Optional[float] = None,
    blot_force: Optional[int] = None,
    humidity_pct: Optional[float] = None,
    temperature_c: Optional[float] = None,
    plunge_date: Optional[str] = None,
    prepared_by: Optional[str] = None,
    ice_quality_notes: Optional[str] = None,
    clipped: bool = False,
    rack_location: Optional[str] = None,
    puck_location: Optional[str] = None,
    box_id: Optional[str] = None,
    box_position: Optional[int] = None,
    status: str = "available"
) -> str:
    """Add a new grid to the database."""
    init_database()
    conn = get_connection()
    cursor = conn.cursor()

    grid_id = generate_grid_id(sample_name)

    if plunge_date is None:
        plunge_date = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("""
        INSERT INTO grids (
            id, sample_name, concentration_nm, grid_type,
            glow_discharge_sec, glow_discharge_ma,
            blot_time_sec, blot_force, humidity_pct, temperature_c,
            plunge_date, prepared_by, ice_quality_notes,
            clipped, rack_location, puck_location, box_id, box_position,
            status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        grid_id, sample_name, concentration_nm, grid_type,
        glow_discharge_sec, glow_discharge_ma,
        blot_time_sec, blot_force, humidity_pct, temperature_c,
        plunge_date, prepared_by, ice_quality_notes,
        1 if clipped else 0, rack_location, puck_location, box_id, box_position,
        status
    ))

    conn.commit()
    conn.close()

    return grid_id


def list_grids(
    sample: Optional[str] = None,
    status: Optional[str] = None,
    clipped_only: bool = False,
    unclipped_only: bool = False,
    rack: Optional[str] = None,
    puck: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> List[Dict]:
    """List grids with optional filters."""
    init_database()
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT id, sample_name, concentration_nm, grid_type, plunge_date,
               prepared_by, clipped, rack_location, puck_location, status
        FROM grids WHERE 1=1
    """
    params = []

    if sample:
        query += " AND sample_name LIKE ?"
        params.append(f"%{sample}%")

    if status:
        query += " AND status = ?"
        params.append(status)

    if clipped_only:
        query += " AND clipped = 1"

    if unclipped_only:
        query += " AND clipped = 0"

    if rack:
        query += " AND rack_location LIKE ?"
        params.append(f"%{rack}%")

    if puck:
        query += " AND puck_location LIKE ?"
        params.append(f"%{puck}%")

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_grid(grid_id: str) -> Optional[Dict]:
    """Get a single grid by ID."""
    init_database()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM grids WHERE id = ?", (grid_id,))
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


def find_grids(query: str, limit: int = 50) -> List[Dict]:
    """Search grids by any field."""
    init_database()
    conn = get_connection()
    cursor = conn.cursor()

    search = f"%{query}%"
    cursor.execute("""
        SELECT id, sample_name, concentration_nm, grid_type, plunge_date,
               prepared_by, clipped, rack_location, puck_location, status
        FROM grids
        WHERE id LIKE ? OR sample_name LIKE ? OR prepared_by LIKE ?
           OR rack_location LIKE ? OR puck_location LIKE ? OR box_id LIKE ?
           OR ice_quality_notes LIKE ? OR screening_notes LIKE ? OR dataset_id LIKE ?
        ORDER BY created_at DESC
        LIMIT ?
    """, (search, search, search, search, search, search, search, search, search, limit))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def update_grid(grid_id: str, **updates) -> bool:
    """Update grid fields."""
    init_database()
    conn = get_connection()
    cursor = conn.cursor()

    # Filter out None values and build update query
    valid_updates = {k: v for k, v in updates.items() if v is not None}

    if not valid_updates:
        return False

    # Add updated_at timestamp
    valid_updates["updated_at"] = datetime.now().isoformat()

    set_clause = ", ".join(f"{k} = ?" for k in valid_updates.keys())
    values = list(valid_updates.values()) + [grid_id]

    cursor.execute(f"UPDATE grids SET {set_clause} WHERE id = ?", values)
    affected = cursor.rowcount

    conn.commit()
    conn.close()

    return affected > 0


def set_clipped(grid_id: str, clipped: bool) -> bool:
    """Set the clipped status of a grid."""
    return update_grid(grid_id, clipped=1 if clipped else 0)


def log_screening(grid_id: str, notes: Optional[str] = None) -> bool:
    """Mark grid as screened and add notes."""
    return update_grid(grid_id, screened=1, screening_notes=notes, status="screening")


def delete_grid(grid_id: str) -> bool:
    """Delete a grid from the database."""
    init_database()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM grids WHERE id = ?", (grid_id,))
    affected = cursor.rowcount

    conn.commit()
    conn.close()

    return affected > 0


def get_stats() -> Dict[str, Any]:
    """Get grid statistics."""
    init_database()
    conn = get_connection()
    cursor = conn.cursor()

    stats = {}

    # Total grids
    cursor.execute("SELECT COUNT(*) FROM grids")
    stats["total"] = cursor.fetchone()[0]

    # By status
    cursor.execute("SELECT status, COUNT(*) as cnt FROM grids GROUP BY status ORDER BY cnt DESC")
    stats["by_status"] = {row["status"]: row["cnt"] for row in cursor.fetchall()}

    # Clipped vs not clipped
    cursor.execute("SELECT clipped, COUNT(*) as cnt FROM grids GROUP BY clipped")
    clipped_counts = {row["clipped"]: row["cnt"] for row in cursor.fetchall()}
    stats["clipped"] = clipped_counts.get(1, 0)
    stats["not_clipped"] = clipped_counts.get(0, 0)

    # By sample (top 10)
    cursor.execute("""
        SELECT sample_name, COUNT(*) as cnt FROM grids
        GROUP BY sample_name ORDER BY cnt DESC LIMIT 10
    """)
    stats["top_samples"] = {row["sample_name"]: row["cnt"] for row in cursor.fetchall()}

    # By rack
    cursor.execute("""
        SELECT rack_location, COUNT(*) as cnt FROM grids
        WHERE rack_location IS NOT NULL AND rack_location != ''
        GROUP BY rack_location ORDER BY rack_location
    """)
    stats["by_rack"] = {row["rack_location"]: row["cnt"] for row in cursor.fetchall()}

    # Recent grids (last 7 days)
    cursor.execute("""
        SELECT COUNT(*) FROM grids
        WHERE date(plunge_date) >= date('now', '-7 days')
    """)
    stats["recent_7d"] = cursor.fetchone()[0]

    conn.close()
    return stats


# =============================================================================
# Output Formatting
# =============================================================================

def format_grid_list(grids: List[Dict]) -> str:
    """Format grid list for display."""
    if not grids:
        return "No grids found"

    lines = []
    lines.append(f"{'ID':<28} {'Sample':<20} {'nM':<8} {'Clip':<5} {'Rack':<8} {'Puck':<8} {'Status':<12}")
    lines.append("-" * 95)

    for g in grids:
        grid_id = g["id"][:27]
        sample = (g["sample_name"] or "")[:19]
        conc = f"{g['concentration_nm']:.0f}" if g["concentration_nm"] else "-"
        clip = "Yes" if g["clipped"] else "No"
        rack = (g["rack_location"] or "-")[:7]
        puck = (g["puck_location"] or "-")[:7]
        status = (g["status"] or "")[:11]

        lines.append(f"{grid_id:<28} {sample:<20} {conc:<8} {clip:<5} {rack:<8} {puck:<8} {status:<12}")

    lines.append(f"\nShowing {len(grids)} grid(s)")
    return "\n".join(lines)


def format_grid_info(grid: Dict) -> str:
    """Format detailed grid information."""
    lines = []
    lines.append("=" * 60)
    lines.append(f"GRID: {grid['id']}")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"Sample:            {grid['sample_name']}")
    lines.append(f"Concentration:     {grid['concentration_nm']} nM" if grid['concentration_nm'] else "Concentration:     -")
    lines.append(f"Grid Type:         {grid['grid_type'] or '-'}")
    lines.append(f"Status:            {grid['status']}")
    lines.append(f"Clipped:           {'Yes' if grid['clipped'] else 'No'}")
    lines.append("")
    lines.append("--- Preparation ---")
    lines.append(f"Plunge Date:       {grid['plunge_date'] or '-'}")
    lines.append(f"Prepared By:       {grid['prepared_by'] or '-'}")
    lines.append(f"Glow Discharge:    {grid['glow_discharge_sec'] or '-'} sec @ {grid['glow_discharge_ma'] or '-'} mA")
    lines.append(f"Blot Time:         {grid['blot_time_sec'] or '-'} sec")
    lines.append(f"Blot Force:        {grid['blot_force'] if grid['blot_force'] is not None else '-'}")
    lines.append(f"Humidity:          {grid['humidity_pct'] or '-'}%")
    lines.append(f"Temperature:       {grid['temperature_c'] or '-'} C")

    if grid['ice_quality_notes']:
        lines.append(f"Ice Quality:       {grid['ice_quality_notes']}")

    lines.append("")
    lines.append("--- Storage ---")
    lines.append(f"Rack Location:     {grid['rack_location'] or '-'}")
    lines.append(f"Puck Location:     {grid['puck_location'] or '-'}")
    lines.append(f"Box ID:            {grid['box_id'] or '-'}")
    lines.append(f"Box Position:      {grid['box_position'] if grid['box_position'] is not None else '-'}")

    lines.append("")
    lines.append("--- Screening ---")
    lines.append(f"Screened:          {'Yes' if grid['screened'] else 'No'}")
    if grid['screening_notes']:
        lines.append(f"Screening Notes:   {grid['screening_notes']}")
    if grid['dataset_id']:
        lines.append(f"Dataset ID:        {grid['dataset_id']}")

    lines.append("")
    lines.append(f"Created:           {grid['created_at']}")
    lines.append(f"Updated:           {grid['updated_at']}")

    return "\n".join(lines)


def format_stats(stats: Dict) -> str:
    """Format statistics for display."""
    lines = []
    lines.append("=" * 60)
    lines.append("GRID STATISTICS")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"Total grids:       {stats['total']}")
    lines.append(f"Clipped:           {stats['clipped']}")
    lines.append(f"Not clipped:       {stats['not_clipped']}")
    lines.append(f"Prepared (7 days): {stats['recent_7d']}")

    if stats['by_status']:
        lines.append("")
        lines.append("By Status:")
        for status, count in stats['by_status'].items():
            lines.append(f"  {status or 'unknown':<15} {count}")

    if stats['top_samples']:
        lines.append("")
        lines.append("Top Samples:")
        for sample, count in stats['top_samples'].items():
            lines.append(f"  {sample:<25} {count}")

    if stats['by_rack']:
        lines.append("")
        lines.append("By Rack:")
        for rack, count in stats['by_rack'].items():
            lines.append(f"  {rack:<15} {count}")

    return "\n".join(lines)


def format_json(data: Any) -> str:
    """Format data as JSON."""
    return json.dumps(data, indent=2, default=str)


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Grid Tracker - Track cryo-EM grid preparation and storage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s add --sample "Pol2-TFIIS" --conc 500 --grid-type "Quantifoil R1.2/1.3 Cu 300"
  %(prog)s add --sample "Complex1" --conc 300 --blot 3 --force 0 --humidity 100 --prepared-by Lucas
  %(prog)s list --sample "Pol2"
  %(prog)s list --status available --clipped
  %(prog)s info G_Pol2_TFIIS_240115_143022
  %(prog)s clip G_Pol2_TFIIS_240115_143022
  %(prog)s screen G_Pol2_TFIIS_240115_143022 --notes "Good ice, visible particles"
  %(prog)s update G_Pol2_TFIIS_240115_143022 --rack A1 --puck P3
  %(prog)s stats
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Add command
    add_parser = subparsers.add_parser('add', help='Add a new grid')
    add_parser.add_argument('--sample', '-s', required=True, help='Sample name')
    add_parser.add_argument('--conc', '-c', type=float, help='Concentration in nM')
    add_parser.add_argument('--grid-type', '-g', help='Grid type (e.g., "Quantifoil R1.2/1.3 Cu 300")')
    add_parser.add_argument('--glow-sec', type=float, help='Glow discharge time in seconds')
    add_parser.add_argument('--glow-ma', type=float, help='Glow discharge current in mA')
    add_parser.add_argument('--blot', type=float, help='Blot time in seconds')
    add_parser.add_argument('--force', type=int, help='Blot force')
    add_parser.add_argument('--humidity', type=float, help='Humidity percentage')
    add_parser.add_argument('--temp', type=float, help='Temperature in Celsius')
    add_parser.add_argument('--date', help='Plunge date (YYYY-MM-DD), defaults to today')
    add_parser.add_argument('--prepared-by', '-p', help='Who prepared the grid')
    add_parser.add_argument('--ice-notes', help='Ice quality notes')
    add_parser.add_argument('--clipped', action='store_true', help='Mark as clipped')
    add_parser.add_argument('--rack', help='Rack location')
    add_parser.add_argument('--puck', help='Puck location')
    add_parser.add_argument('--box', help='Box ID')
    add_parser.add_argument('--box-pos', type=int, help='Position in box')
    add_parser.add_argument('--status', default='available', choices=GRID_STATUSES, help='Initial status')
    add_parser.add_argument('--json', action='store_true', help='Output as JSON')

    # List command
    list_parser = subparsers.add_parser('list', help='List grids')
    list_parser.add_argument('--sample', '-s', help='Filter by sample name')
    list_parser.add_argument('--status', choices=GRID_STATUSES, help='Filter by status')
    list_parser.add_argument('--clipped', action='store_true', help='Show only clipped grids')
    list_parser.add_argument('--unclipped', action='store_true', help='Show only unclipped grids')
    list_parser.add_argument('--rack', help='Filter by rack location')
    list_parser.add_argument('--puck', help='Filter by puck location')
    list_parser.add_argument('--limit', '-l', type=int, default=50, help='Limit results')
    list_parser.add_argument('--offset', '-o', type=int, default=0, help='Offset for pagination')
    list_parser.add_argument('--json', action='store_true', help='Output as JSON')

    # Info command
    info_parser = subparsers.add_parser('info', help='Show grid details')
    info_parser.add_argument('grid_id', help='Grid ID')
    info_parser.add_argument('--json', action='store_true', help='Output as JSON')

    # Find command
    find_parser = subparsers.add_parser('find', help='Search grids')
    find_parser.add_argument('query', help='Search query')
    find_parser.add_argument('--limit', '-l', type=int, default=50, help='Limit results')
    find_parser.add_argument('--json', action='store_true', help='Output as JSON')

    # Clip command
    clip_parser = subparsers.add_parser('clip', help='Mark grid as clipped')
    clip_parser.add_argument('grid_id', help='Grid ID')

    # Unclip command
    unclip_parser = subparsers.add_parser('unclip', help='Mark grid as not clipped')
    unclip_parser.add_argument('grid_id', help='Grid ID')

    # Screen command
    screen_parser = subparsers.add_parser('screen', help='Log screening results')
    screen_parser.add_argument('grid_id', help='Grid ID')
    screen_parser.add_argument('--notes', '-n', help='Screening notes')

    # Update command
    update_parser = subparsers.add_parser('update', help='Update grid fields')
    update_parser.add_argument('grid_id', help='Grid ID')
    update_parser.add_argument('--sample', help='Sample name')
    update_parser.add_argument('--conc', type=float, help='Concentration in nM')
    update_parser.add_argument('--rack', help='Rack location')
    update_parser.add_argument('--puck', help='Puck location')
    update_parser.add_argument('--box', help='Box ID')
    update_parser.add_argument('--box-pos', type=int, help='Box position')
    update_parser.add_argument('--status', choices=GRID_STATUSES, help='Status')
    update_parser.add_argument('--dataset', help='Dataset ID')
    update_parser.add_argument('--ice-notes', help='Ice quality notes')
    update_parser.add_argument('--screening-notes', help='Screening notes')

    # Delete command
    delete_parser = subparsers.add_parser('delete', help='Delete a grid')
    delete_parser.add_argument('grid_id', help='Grid ID')
    delete_parser.add_argument('--force', '-f', action='store_true', help='Skip confirmation')

    # Stats command
    stats_parser = subparsers.add_parser('stats', help='Show statistics')
    stats_parser.add_argument('--json', action='store_true', help='Output as JSON')

    # Grid types command
    types_parser = subparsers.add_parser('types', help='List common grid types')

    args = parser.parse_args()

    if args.command == 'add':
        grid_id = add_grid(
            sample_name=args.sample,
            concentration_nm=args.conc,
            grid_type=args.grid_type,
            glow_discharge_sec=args.glow_sec,
            glow_discharge_ma=args.glow_ma,
            blot_time_sec=args.blot,
            blot_force=args.force,
            humidity_pct=args.humidity,
            temperature_c=args.temp,
            plunge_date=args.date,
            prepared_by=args.prepared_by,
            ice_quality_notes=args.ice_notes,
            clipped=args.clipped,
            rack_location=args.rack,
            puck_location=args.puck,
            box_id=args.box,
            box_position=args.box_pos,
            status=args.status
        )
        if args.json:
            print(format_json({"id": grid_id, "status": "created"}))
        else:
            print(f"Grid added: {grid_id}")

    elif args.command == 'list':
        grids = list_grids(
            sample=args.sample,
            status=args.status,
            clipped_only=args.clipped,
            unclipped_only=args.unclipped,
            rack=args.rack,
            puck=args.puck,
            limit=args.limit,
            offset=args.offset
        )
        if args.json:
            print(format_json(grids))
        else:
            print(format_grid_list(grids))

    elif args.command == 'info':
        grid = get_grid(args.grid_id)
        if grid:
            if args.json:
                print(format_json(grid))
            else:
                print(format_grid_info(grid))
        else:
            print(f"Grid not found: {args.grid_id}", file=sys.stderr)
            return 1

    elif args.command == 'find':
        grids = find_grids(args.query, limit=args.limit)
        if args.json:
            print(format_json(grids))
        else:
            print(format_grid_list(grids))

    elif args.command == 'clip':
        if set_clipped(args.grid_id, True):
            print(f"Grid marked as clipped: {args.grid_id}")
        else:
            print(f"Grid not found: {args.grid_id}", file=sys.stderr)
            return 1

    elif args.command == 'unclip':
        if set_clipped(args.grid_id, False):
            print(f"Grid marked as not clipped: {args.grid_id}")
        else:
            print(f"Grid not found: {args.grid_id}", file=sys.stderr)
            return 1

    elif args.command == 'screen':
        if log_screening(args.grid_id, notes=args.notes):
            print(f"Screening logged for: {args.grid_id}")
        else:
            print(f"Grid not found: {args.grid_id}", file=sys.stderr)
            return 1

    elif args.command == 'update':
        updates = {}
        if args.sample:
            updates['sample_name'] = args.sample
        if args.conc is not None:
            updates['concentration_nm'] = args.conc
        if args.rack:
            updates['rack_location'] = args.rack
        if args.puck:
            updates['puck_location'] = args.puck
        if args.box:
            updates['box_id'] = args.box
        if args.box_pos is not None:
            updates['box_position'] = args.box_pos
        if args.status:
            updates['status'] = args.status
        if args.dataset:
            updates['dataset_id'] = args.dataset
        if args.ice_notes:
            updates['ice_quality_notes'] = args.ice_notes
        if args.screening_notes:
            updates['screening_notes'] = args.screening_notes

        if not updates:
            print("No updates specified", file=sys.stderr)
            return 1

        if update_grid(args.grid_id, **updates):
            print(f"Grid updated: {args.grid_id}")
        else:
            print(f"Grid not found or no changes: {args.grid_id}", file=sys.stderr)
            return 1

    elif args.command == 'delete':
        if not args.force:
            grid = get_grid(args.grid_id)
            if not grid:
                print(f"Grid not found: {args.grid_id}", file=sys.stderr)
                return 1
            confirm = input(f"Delete grid {args.grid_id} ({grid['sample_name']})? [y/N] ")
            if confirm.lower() != 'y':
                print("Cancelled")
                return 0

        if delete_grid(args.grid_id):
            print(f"Grid deleted: {args.grid_id}")
        else:
            print(f"Grid not found: {args.grid_id}", file=sys.stderr)
            return 1

    elif args.command == 'stats':
        stats = get_stats()
        if args.json:
            print(format_json(stats))
        else:
            print(format_stats(stats))

    elif args.command == 'types':
        print("Common Grid Types:")
        print("-" * 40)
        for gt in GRID_TYPES:
            print(f"  {gt}")

    else:
        parser.print_help()

    return 0


if __name__ == "__main__":
    sys.exit(main())
