#!/usr/bin/env python3
"""
Import proteins from Notion JSON dump to LabBook registry.
"""

import json
import os
import subprocess
import sys

def run_labbook_cmd(args, workdir=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cmd/labbookCLI")):
    """Run a labbook CLI command."""
    env = os.environ.copy()
    cmd = ["go", "run", "main.go"] + args
    result = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, env=env)
    return result.returncode, result.stdout, result.stderr


def import_protein(protein):
    """Import a single protein to LabBook."""
    name = protein.get("name", "")
    if not name:
        return False, "No name"
    
    # Build the command
    args = [
        "registry", "create",
        "--name", name,
        "--kind", "Protein preparation",
    ]
    
    # Add species
    species = protein.get("species")
    if species:
        args.extend(["--species", species])
    
    # Add label as aliquot-label
    label = protein.get("label")
    if label:
        args.extend(["--aliquot-label", label])
    
    # Add concentrations
    conc_mg_ml = protein.get("conc_mg_ml")
    if conc_mg_ml and str(conc_mg_ml).strip():
        try:
            val = float(str(conc_mg_ml).replace(",", "."))
            args.extend(["--concentration-mg-ml", str(val)])
        except ValueError:
            pass
    
    conc_um = protein.get("conc_um")
    if conc_um and str(conc_um).strip():
        try:
            val = float(str(conc_um).replace(",", "."))
            args.extend(["--concentration-um", str(val)])
        except ValueError:
            pass
    
    # Add A260/A280
    a260_280 = protein.get("a260_280")
    if a260_280 and str(a260_280).strip():
        try:
            val = float(str(a260_280).replace(",", "."))
            args.extend(["--a260-a280", str(val)])
        except ValueError:
            pass
    
    # Add expression system
    expression = protein.get("expression_system")
    if expression and str(expression).strip():
        args.extend(["--expression-system", str(expression)])
    
    # Add storage buffer
    buffer = protein.get("buffer")
    if buffer and str(buffer).strip():
        args.extend(["--storage-buffer", str(buffer)])
    
    # Add aliquot size
    aliquot_size = protein.get("aliquot_size")
    if aliquot_size and str(aliquot_size).strip():
        try:
            # Handle "4 uL" or "4" formats
            val_str = str(aliquot_size).replace("uL", "").replace("µL", "").strip()
            if val_str and val_str[0].isdigit():
                val = float(val_str.split()[0])
                args.extend(["--aliquot-size-ul", str(val)])
        except (ValueError, IndexError):
            pass
    
    # Add aliquot count
    aliquot_count = protein.get("aliquot_count")
    if aliquot_count and str(aliquot_count).strip():
        try:
            val_str = str(aliquot_count).replace("~", "").strip()
            if val_str and val_str[0].isdigit():
                val = int(val_str.split()[0])
                args.extend(["--aliquot-count", str(val)])
        except (ValueError, IndexError):
            pass
    
    # Add location
    location = protein.get("location")
    if location and str(location).strip():
        args.extend(["--location", str(location)])
    
    # Add prepped by
    prepped_by = protein.get("prepped_by")
    if prepped_by and str(prepped_by).strip():
        args.extend(["--prepped-by", str(prepped_by)])
    
    # Add prepped on date
    prepped_on = protein.get("prepped_on")
    if prepped_on and str(prepped_on).strip():
        args.extend(["--prepped-on", str(prepped_on)])
    
    # Add availability
    available = protein.get("available")
    if available is not None:
        args.extend(["--available", "yes" if available else "no"])
    
    # Add description with Notion ID for reference
    notion_id = protein.get("notion_id", "")
    desc_parts = []
    if notion_id:
        desc_parts.append(f"Notion ID: {notion_id}")
    if desc_parts:
        args.extend(["--description", "; ".join(desc_parts)])
    
    # Run the command
    returncode, stdout, stderr = run_labbook_cmd(args)
    
    if returncode == 0:
        return True, stdout.strip()
    else:
        return False, stderr.strip() or stdout.strip()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Import proteins to LabBook")
    parser.add_argument("json_file", help="JSON file with proteins")
    parser.add_argument("--dry-run", action="store_true", help="Show commands without executing")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of imports")
    args = parser.parse_args()
    
    # Load proteins
    with open(args.json_file) as f:
        proteins = json.load(f)
    
    print(f"Loaded {len(proteins)} proteins from {args.json_file}")
    
    if args.limit:
        proteins = proteins[:args.limit]
        print(f"Limited to {args.limit} proteins")
    
    success = 0
    failed = 0
    
    for i, protein in enumerate(proteins):
        name = protein.get("name", "Unknown")
        species = protein.get("species", "")
        avail = "✓" if protein.get("available") else "✗"
        
        if args.dry_run:
            print(f"[{i+1}/{len(proteins)}] Would import: {avail} {name} ({species})")
            continue
        
        ok, msg = import_protein(protein)
        if ok:
            success += 1
            print(f"[{i+1}/{len(proteins)}] ✓ {name}")
        else:
            failed += 1
            print(f"[{i+1}/{len(proteins)}] ✗ {name}: {msg}")
    
    if not args.dry_run:
        print(f"\nImported: {success}, Failed: {failed}")


if __name__ == "__main__":
    main()
