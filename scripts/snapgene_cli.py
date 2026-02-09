#!/usr/bin/env python3
"""
SnapGene Reader CLI - Parse SnapGene .dna files.

Extracts sequence, features, and metadata from SnapGene files.
Outputs GenBank format or JSON.
"""

import argparse
import json
import sys
from pathlib import Path

try:
    from snapgene_reader import snapgene_file_to_dict, snapgene_file_to_seqrecord
    from Bio import SeqIO
    from Bio.SeqRecord import SeqRecord
except ImportError:
    print("Error: snapgene_reader not installed. Run: pip install snapgene_reader", file=sys.stderr)
    sys.exit(1)


def read_snapgene(filepath: str) -> tuple[dict, SeqRecord]:
    """Read SnapGene file, return both dict and SeqRecord."""
    data = snapgene_file_to_dict(filepath)
    record = snapgene_file_to_seqrecord(filepath)
    return data, record


def format_features_table(record: SeqRecord) -> str:
    """Format features as a table."""
    lines = []
    lines.append(f"{'Type':<15} {'Start':>7} {'End':>7} {'Strand':<6} {'Name'}")
    lines.append("-" * 60)

    for feat in sorted(record.features, key=lambda f: int(f.location.start)):
        name = feat.qualifiers.get('label', [feat.qualifiers.get('gene', [feat.type])[0]])[0]
        strand = '+' if feat.location.strand == 1 else '-' if feat.location.strand == -1 else '.'
        start = int(feat.location.start) + 1  # 1-indexed
        end = int(feat.location.end)
        lines.append(f"{feat.type:<15} {start:>7} {end:>7} {strand:<6} {name}")

    return '\n'.join(lines)


def export_genbank(record: SeqRecord, output_path: str) -> None:
    """Export SeqRecord to GenBank format."""
    with open(output_path, 'w') as f:
        SeqIO.write(record, f, 'genbank')


def export_fasta(record: SeqRecord, output_path: str) -> None:
    """Export SeqRecord to FASTA format."""
    with open(output_path, 'w') as f:
        SeqIO.write(record, f, 'fasta')


def main():
    parser = argparse.ArgumentParser(
        description="Parse SnapGene .dna files and extract sequence/features.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s 438-C.dna                      # Show summary
  %(prog)s 438-C.dna --features           # List all features
  %(prog)s 438-C.dna --sequence           # Print DNA sequence
  %(prog)s 438-C.dna --export-gb out.gb   # Convert to GenBank
  %(prog)s 438-C.dna --export-fasta out.fa # Convert to FASTA
  %(prog)s 438-C.dna --json               # Full output as JSON
        """
    )

    parser.add_argument('file', help='Path to SnapGene .dna file')
    parser.add_argument('--features', '-f', action='store_true',
                        help='List all features')
    parser.add_argument('--sequence', '-s', action='store_true',
                        help='Print DNA sequence')
    parser.add_argument('--export-gb', '-g', metavar='FILE',
                        help='Export to GenBank format')
    parser.add_argument('--export-fasta', '-a', metavar='FILE',
                        help='Export to FASTA format')
    parser.add_argument('--json', '-j', action='store_true',
                        help='Output as JSON')

    args = parser.parse_args()

    # Check file exists
    if not Path(args.file).exists():
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        return 1

    try:
        data, record = read_snapgene(args.file)
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        return 1

    # JSON output
    if args.json:
        output = {
            'name': record.name,
            'description': record.description,
            'length': len(record.seq),
            'sequence': str(record.seq),
            'features': [
                {
                    'type': f.type,
                    'start': int(f.location.start) + 1,
                    'end': int(f.location.end),
                    'strand': '+' if f.location.strand == 1 else '-' if f.location.strand == -1 else '.',
                    'qualifiers': {k: v[0] if len(v) == 1 else v for k, v in f.qualifiers.items()}
                }
                for f in record.features
            ]
        }
        print(json.dumps(output, indent=2))
        return 0

    # Export GenBank
    if args.export_gb:
        export_genbank(record, args.export_gb)
        print(f"Exported to {args.export_gb}")
        return 0

    # Export FASTA
    if args.export_fasta:
        export_fasta(record, args.export_fasta)
        print(f"Exported to {args.export_fasta}")
        return 0

    # Sequence only
    if args.sequence:
        print(str(record.seq))
        return 0

    # Features table
    if args.features:
        print(f"Features in {Path(args.file).name}:")
        print()
        print(format_features_table(record))
        return 0

    # Default: summary
    print(f"SnapGene File: {Path(args.file).name}")
    print("=" * 50)
    print(f"Name: {record.name}")
    print(f"Length: {len(record.seq):,} bp")
    print(f"Features: {len(record.features)}")
    print(f"Topology: {'circular' if 'circular' in record.annotations.get('topology', '').lower() else 'linear'}")

    if record.description:
        print(f"Description: {record.description}")

    # Show feature summary by type
    feat_counts = {}
    for f in record.features:
        feat_counts[f.type] = feat_counts.get(f.type, 0) + 1

    print()
    print("Feature types:")
    for ftype, count in sorted(feat_counts.items()):
        print(f"  {ftype}: {count}")

    print()
    print("Use --features for full feature list, --export-gb to convert to GenBank")

    return 0


if __name__ == "__main__":
    sys.exit(main())
