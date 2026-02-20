---
name: orfverifier
description: Verify open reading frames (ORFs) in plasmid sequences. Use when the user asks about verifying protein coding sequences, checking if an ORF is present in a plasmid, finding where a protein is encoded, or doing six-frame translation analysis.
allowed-tools: Bash(orf_verifier_cli:*), Bash(python:*)
---

# ORF Verifier Tool

Verify that expected amino acid sequences are present in plasmid DNA using six-frame translation.

## CLI Usage

Use the CLI at `scripts/orf_verifier_cli.py`:

### Basic Verification
```bash
scripts/orf_verifier_cli.py --plasmid /path/to/plasmid.gb --aa-sequence "MSKGEELFTGVVPILVELDGDVNGHKFSVSGEGEGDATYGKLTLKFICTTGKLPVPWPTLVTTLTYGVQCFSRYPDHMKQHDFFKSAMPEGYVQERTIFFKDDGNYKTRAEVKFEGDTLVNRIELKGIDFKEDGNILGHKLEYNYNSHNVYIMADKQKNGIKVNFKIRHNIEDGSVQLADHYQQNTPIGDGPVLLPDNHYLSTQSALSKDPNEKRDHMVLLEFVTAAGITLGMDELYK" --name "GFP"
```

### With NCBI Accession
```bash
scripts/orf_verifier_cli.py --accession MN514974 --aa-sequence "MHHHHHH..." --name "His6-protein"
```

### JSON Output
```bash
scripts/orf_verifier_cli.py --plasmid plasmid.fasta --aa-sequence "MHHHHHH..." --json
```

## Options

- `--plasmid, -p FILE`: Path to plasmid file (FASTA or GenBank format)
- `--accession, -a ID`: NCBI accession number to fetch
- `--aa-sequence, -s SEQUENCE`: Amino acid sequence to verify (required)
- `--name, -n NAME`: Name for the ORF (default: Query)
- `--allow-alt-start`: Allow alternative start codons (GTG, TTG)
- `--min-identity FLOAT`: Minimum identity threshold (0-1, default: 1.0)
- `--max-mismatches INT`: Maximum allowed amino acid mismatches (default: 0)
- `--disallow-internal-met`: Disallow internal methionine start codons
- `--json`: Output results as JSON
- `--list-tags`: List available tag definitions

## Verification Results

### Status Types
- **verified**: ORF found at exactly one location
- **not-found**: ORF not found in any reading frame
- **indeterminate**: Multiple possible locations found

### Placement Information
- **Strand**: Plus (+) or Minus (-) strand
- **Frame**: Reading frame (0, 1, or 2)
- **Position**: Nucleotide start and end positions (1-indexed in output)
- **Wraps origin**: Whether the ORF crosses the plasmid origin

## Auto-Detected Tags

The tool automatically detects common protein tags:
- His6, His10 (polyhistidine)
- N-His6-TEV, N-His6-MBP-N10-TEV
- StrepII, FLAG, HA, Myc
- TEV site, HRV 3C site
- SUMO
- GGGGS linkers

View all tags:
```bash
scripts/orf_verifier_cli.py --list-tags
```

## Annotation Verification Mode

Batch verify all CDS annotations in pLannotate-annotated GenBank files against UniProt reference sequences.

### Usage

```bash
# Verify single plasmid
python3 scripts/orf_verifier_cli.py verify-annotations plasmid.gbk --targets-only

# Verify multiple files
python3 scripts/orf_verifier_cli.py verify-annotations *.gbk --targets-only --summary

# Verify directory of sequencing results
python3 scripts/orf_verifier_cli.py verify-annotations sequencing_results/ --targets-only -o report.md
```

### Options

- `--targets-only`: Only verify target proteins (HUMAN, MOUSE, BOVIN), skip E. coli vector components
- `--organism, -O CODE`: Filter to specific organism (e.g., HUMAN)
- `--summary`: Show only summary, not per-protein details
- `--json`: Output as JSON
- `--output, -o FILE`: Write to file instead of stdout

### Result Status

- **PASS**: 100% identity to UniProt reference (includes valid N/C-terminal truncations)
- **FAIL**: Less than 100% identity (mutations, deletions, insertions)
- **ERROR**: Could not verify (UniProt lookup failed, translation error)

### Example Output

```
============================================================
ANNOTATION VERIFICATION SUMMARY
============================================================
Files processed: 10
Total PASS: 42
Total FAIL: 2
Total ERROR: 0

[PASS] plasmid_1.gbk: 7/7 passed
[FAIL] plasmid_2.gbk: 3/4 passed
```

### Handling Truncations

The tool correctly handles N-terminal and C-terminal truncations as PASS if the expressed region is 100% identical to UniProt. Notes indicate truncation position:

```
[PASS] MED14_HUMAN (O60244)
       Length: 1409 aa (UniProt: 1454 aa)
       Identity: 100.0%
       Note: N-term truncated: starts at UniProt position 46
```
