#!/usr/bin/env python3
"""
Complex Formation CLI - Simplified interface for complex assembly calculations.

Usage:
    complex_cli.py ec_star --pol2 5.2uM --volume 100
    complex_cli.py ec_star --pol2 5.2uM --volume 100 --exclude RTF1,P-TEFb
    complex_cli.py ec_star --pol2 5.2uM --volume 100 --add "TFIIS:1.5x:50uM"
    complex_cli.py ec_star --pol2 5.2uM --volume 100 --pmol 70
    complex_cli.py list  # List available presets
"""

import argparse
import sys
import subprocess
import re
from pathlib import Path

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

PRESETS_PATH = Path(__file__).parent.parent / "complex_presets.yaml"

def load_presets():
    """Load presets from YAML file."""
    if not YAML_AVAILABLE:
        print("Error: PyYAML not installed. Run: pip install pyyaml", file=sys.stderr)
        sys.exit(1)
    
    if not PRESETS_PATH.exists():
        print(f"Error: Presets file not found: {PRESETS_PATH}", file=sys.stderr)
        sys.exit(1)
    
    with open(PRESETS_PATH) as f:
        return yaml.safe_load(f)

def query_notion_protein(query: str, prefer_stock_uM: float = None) -> dict:
    """Query LabBook registry for protein stock info."""
    cmd = [
        "go", "run", "main.go",
        "registry", "list", "--kind", "Protein preparation", "--q", query,
    ]
    cwd = str(Path(__file__).parent.parent / "cmd" / "labbookCLI")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=cwd)
        lines = result.stdout.strip().split('\n')
        
        matches = []
        for line in lines:
            if query.lower() in line.lower():
                # Parse the line - format: Name  Species  mg/mL  µM  aliquots  Available
                # Find all numeric values in the line
                numbers = re.findall(r'(?<!\w)([\d.]+)(?!\w)', line)
                # The µM value is typically the second number (after mg/mL)
                # and should be reasonable (1-500 µM range)
                for num_str in numbers[1:3]:  # Check 2nd and 3rd numbers
                    try:
                        um = float(num_str)
                        if 5 < um < 500:  # µM range (higher threshold to skip mg/mL)
                            matches.append({
                                'name': query,
                                'concentration_uM': um,
                                'line': line
                            })
                            break
                    except ValueError:
                        continue
        
        if not matches:
            return None
        
        # If prefer_stock_uM specified, find closest match (within 20% tolerance)
        if prefer_stock_uM and len(matches) > 1:
            # First try exact match (within 5%)
            for m in matches:
                if abs(m['concentration_uM'] - prefer_stock_uM) / prefer_stock_uM < 0.05:
                    return m
            # Then sort by distance
            matches.sort(key=lambda m: abs(m['concentration_uM'] - prefer_stock_uM))
        
        return matches[0]
    
    except Exception as e:
        print(f"Warning: Could not query Notion for {query}: {e}", file=sys.stderr)
        return None

def parse_concentration(conc_str: str) -> float:
    """Parse concentration string like '5.2uM' to float µM."""
    match = re.match(r'([\d.]+)\s*(uM|µM|um|nM|mM)?', conc_str, re.IGNORECASE)
    if not match:
        raise ValueError(f"Cannot parse concentration: {conc_str}")
    
    value = float(match.group(1))
    unit = (match.group(2) or 'uM').lower()
    
    if unit in ('um', 'µm'):
        return value
    elif unit == 'nm':
        return value / 1000
    elif unit == 'mm':
        return value * 1000
    else:
        return value

def build_reactor_command(preset: dict, pol2_conc: float, volume: float, 
                          pmol: float, exclude: list, add: list) -> list:
    """Build reactor_cli.py command from preset."""
    
    components = preset['components'].copy()
    
    # Filter excluded components
    if exclude:
        exclude_lower = [e.lower() for e in exclude]
        components = [c for c in components if c['name'].lower() not in exclude_lower]
    
    # Build protein arguments
    protein_args = []
    reference_pmol = pmol
    
    for comp in components:
        name = comp['name']
        ratio = comp['ratio']
        
        # Parse ratio
        if isinstance(ratio, str) and ratio.endswith('x'):
            ratio_val = float(ratio[:-1])
        else:
            ratio_val = float(ratio)
        
        # Get concentration
        if name == "Pol II":
            stock_uM = pol2_conc
        else:
            # Try to get from Notion
            notion_result = query_notion_protein(
                comp.get('notion_query', name),
                comp.get('prefer_stock_uM')
            )
            if notion_result:
                stock_uM = notion_result['concentration_uM']
            elif comp.get('prefer_stock_uM'):
                stock_uM = comp['prefer_stock_uM']
                print(f"Warning: Using preset concentration for {name}: {stock_uM} µM", file=sys.stderr)
            else:
                print(f"Error: No concentration found for {name}", file=sys.stderr)
                sys.exit(1)
        
        # Build buffer string
        buffer_parts = []
        for buf_name, buf_conc in comp.get('buffer', {}).items():
            # Parse concentration
            if isinstance(buf_conc, str):
                match = re.match(r'([\d.]+)\s*(%|mM|uM)?', buf_conc)
                if match:
                    val = match.group(1)
                    unit = match.group(2) or 'mM'
                    if unit == '%':
                        buffer_parts.append(f"{buf_name}/{val}%")
                    else:
                        buffer_parts.append(f"{buf_name}/{val}{unit}")
            else:
                buffer_parts.append(f"{buf_name}/{buf_conc}mM")
        
        buffer_str = ','.join(buffer_parts) if buffer_parts else ''
        
        # Build protein spec
        protein_spec = f"{name}:{ratio_val}x:stock={stock_uM}uM"
        if buffer_str:
            protein_spec += f":buffer={buffer_str}"
        
        protein_args.extend(['--protein', protein_spec])
    
    # Add extra components
    for add_spec in add:
        protein_args.extend(['--protein', add_spec])
    
    # Build buffer arguments from final_buffer
    buffer_args = []
    stocks = {
        'HEPES_pH_7.4': '1M', 'HEPES': '1M',
        'NaCl': '5M',
        'MgCl2': '1M',
        'TCEP': '0.5M',
        'glycerol': '50%',
        'DTT': '1M',
        'ZnCl2': '0.5M'
    }
    
    for buf_name, final_conc in preset.get('final_buffer', {}).items():
        stock = stocks.get(buf_name, '1M')
        if isinstance(final_conc, str):
            match = re.match(r'([\d.]+)\s*(%|mM|uM)?', final_conc)
            if match:
                val = match.group(1)
                unit = match.group(2) or 'mM'
                buffer_args.extend(['--buffer', f"{buf_name}:{stock}->{val}{unit}"])
        else:
            buffer_args.extend(['--buffer', f"{buf_name}:{stock}->{final_conc}mM"])
    
    # Build full command
    cmd = [
        sys.executable,
        str(Path(__file__).parent / "reactor_cli.py"),
        '--reference', f'{reference_pmol}pmol',
        '--volume', str(volume),
        '--mode', 'compensation',
        '--fold', '5'
    ] + protein_args + buffer_args
    
    return cmd

def format_output(stdout: str, preset_name: str, preset: dict) -> str:
    """Format reactor output nicely."""
    lines = [
        f"# {preset_name.upper()}: {preset.get('description', '')}",
        "",
        stdout,
        "",
        "---",
        f"Final conditions: {', '.join(f'{k}: {v}' for k, v in preset.get('final_buffer', {}).items())}"
    ]
    return '\n'.join(lines)

def list_presets(presets: dict):
    """List available presets."""
    print("\nAvailable presets:\n")
    for name, preset in presets.get('presets', {}).items():
        desc = preset.get('description', '')
        components = [c['name'] for c in preset.get('components', [])]
        
        if preset.get('extends'):
            print(f"  {name}")
            print(f"    Extends: {preset['extends']}")
            if preset.get('only'):
                print(f"    Only: {', '.join(preset['only'])}")
            if preset.get('add'):
                print(f"    Adds: {', '.join(c['name'] for c in preset['add'])}")
        else:
            print(f"  {name}")
            print(f"    {desc}")
            print(f"    Components: {', '.join(components)}")
        print()

def main():
    parser = argparse.ArgumentParser(
        description='Complex formation calculator with presets',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s ec_star --pol2 5.2uM
  %(prog)s ec_star --pol2 5.2uM --volume 100 --pmol 70
  %(prog)s ec_star --pol2 5.2uM --exclude RTF1,P-TEFb
  %(prog)s list
        """
    )
    
    parser.add_argument('preset', nargs='?', help='Preset name or "list"')
    parser.add_argument('--pol2', required=False, help='Pol II concentration (e.g., 5.2uM)')
    parser.add_argument('--volume', '-v', type=float, default=100, help='Reaction volume in µL (default: 100)')
    parser.add_argument('--pmol', type=float, default=70, help='Reference pmol for Pol II (default: 70)')
    parser.add_argument('--exclude', '-x', help='Comma-separated list of components to exclude')
    parser.add_argument('--add', '-a', action='append', default=[], help='Additional component (Name:ratio:stockuM)')
    parser.add_argument('--dry-run', action='store_true', help='Show command without running')
    
    args = parser.parse_args()
    
    if not args.preset:
        parser.print_help()
        sys.exit(1)
    
    presets = load_presets()
    
    if args.preset == 'list':
        list_presets(presets)
        sys.exit(0)
    
    if args.preset not in presets.get('presets', {}):
        print(f"Error: Unknown preset '{args.preset}'", file=sys.stderr)
        print(f"Available: {', '.join(presets.get('presets', {}).keys())}", file=sys.stderr)
        sys.exit(1)
    
    if not args.pol2:
        print("Error: --pol2 concentration required", file=sys.stderr)
        sys.exit(1)
    
    preset = presets['presets'][args.preset]
    
    # Handle 'extends' - resolve parent preset
    if preset.get('extends'):
        parent = presets['presets'].get(preset['extends'])
        if parent:
            # Merge parent into current
            merged = parent.copy()
            if preset.get('only'):
                merged['components'] = [c for c in parent['components'] if c['name'] in preset['only']]
            if preset.get('add'):
                merged['components'] = merged.get('components', []) + preset['add']
            merged['description'] = preset.get('description', parent.get('description', ''))
            preset = merged
    
    pol2_conc = parse_concentration(args.pol2)
    exclude = args.exclude.split(',') if args.exclude else []
    
    cmd = build_reactor_command(preset, pol2_conc, args.volume, args.pmol, exclude, args.add)
    
    if args.dry_run:
        print(' \\\n  '.join(cmd))
        sys.exit(0)
    
    # Run reactor_cli
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Error running reactor_cli:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    
    print(format_output(result.stdout, args.preset, preset))

if __name__ == '__main__':
    main()
