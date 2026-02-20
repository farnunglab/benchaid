---
name: constructboundary
description: Predict optimal construct boundaries for protein expression. Use when the user asks about domain boundaries, construct design, truncations, which region of a protein to express, or identifying disordered regions.
allowed-tools: Bash(construct_boundary:*), Bash(go run cmd/construct_boundary:*)
---

# Construct Boundary Predictor

Analyze protein sequences to suggest optimal truncation boundaries for recombinant expression constructs, particularly for structural biology (crystallography, cryo-EM).

## CLI Location

```bash
# Run directly (if built)
cmd/construct_boundary/construct_boundary

# Or via go run
go run cmd/construct_boundary/main.go
```

## Quick Start

```bash
# By UniProt ID
go run cmd/construct_boundary/main.go --uniprot CHD1_HUMAN

# By gene name
go run cmd/construct_boundary/main.go --uniprot CHD1

# Focus on specific region
go run cmd/construct_boundary/main.go --uniprot CHD1_HUMAN --region 1400-1600

# Focus on domain by name
go run cmd/construct_boundary/main.go --uniprot CHD1_HUMAN --region CHCT
```

## Options

| Option | Description |
|--------|-------------|
| `--uniprot` | UniProt ID, entry name (CHD1_HUMAN), or gene name |
| `--sequence` | Raw amino acid sequence (alternative to --uniprot) |
| `--name` | Protein name (required with --sequence) |
| `--region` | Focus region: "500-800" or domain name like "ATPase" |
| `--min-length` | Minimum construct length in aa (default: 100) |
| `--max-length` | Maximum construct length in aa (0 = no limit) |
| `--json` | Output as JSON for programmatic use |
| `--plot` | Write ASCII visualization to file |

## Data Sources

The tool fetches and integrates data from:

| Source | Data |
|--------|------|
| **UniProt** | Sequence, domains, active sites, PTMs, secondary structure |
| **AlphaFold DB** | Per-residue pLDDT confidence scores |
| **PDB** | Existing crystallized/cryo-EM construct boundaries |

Data is cached in `~/.cache/benchaid/` for 30 days.

## Scoring Algorithm

Boundaries are scored (0-100) based on:

| Factor | Weight | Criteria |
|--------|--------|----------|
| Disorder transition | +30 | Boundary at disorder→order transition |
| Domain boundary | +25 | Aligns with Pfam/UniProt domain |
| Loop region | +20 | Low pLDDT flanked by high pLDDT |
| Structured side | +15 | pLDDT > 70 on the construct interior |
| PDB match | +10 | Matches existing structure boundary |

**Penalties:**
- Cuts α-helix or β-strand: -50
- Near active site: -100
- Within 5 residues of PTM: -20

## Output Format

### Text Output (default)

```
CONSTRUCT BOUNDARY PREDICTIONS FOR CHD1_HUMAN (1710 aa)
========================================================

Rank  Region        Length  Score  Rationale
----  ------------  ------  -----  ---------------------------------
1     1431-1510     80      94     domain boundary; high pLDDT side
2     270-443       174     89     domain boundary; PDB boundary
3     614-900       287     85     disorder transition; loop-like region

DISORDERED REGIONS (pLDDT < 50):
  1-45
  168-265
  1520-1710

EXISTING PDB STRUCTURES:
  4O42: 1431-1506 (1.9 Å)
  2EJK: 270-440

Position: |-------------------|-------------------|-------------------|-------------------|
pLDDT:    ..=###==============###==========================================###...........
Disorder: ##....##############...................................................#########
Domains:       ====           ==========================================     ====
Suggested:     1111           22222222222222222222222222222222222222222      3333
```

### JSON Output (--json)

```json
{
  "protein": {
    "uniprot_id": "O14646",
    "name": "CHD1_HUMAN",
    "length": 1710,
    "gene": "CHD1"
  },
  "predictions": [
    {
      "rank": 1,
      "start": 1431,
      "end": 1510,
      "length": 80,
      "score": 94,
      "rationale": "domain boundary, high pLDDT side",
      "evidence": {
        "pdb_match": "4O42",
        "domain": "CHCT",
        "avg_plddt": 89.2,
        "disorder_fraction": 0.02
      }
    }
  ],
  "features": {
    "domains": [...],
    "disordered_regions": [...],
    "pdb_structures": [...],
    "plddt_scores": [...]
  },
  "warnings": [...]
}
```

## Examples

### Design construct for a specific domain

```bash
go run cmd/construct_boundary/main.go --uniprot SETD2_HUMAN --region SET
```

### Find minimal construct with length constraints

```bash
go run cmd/construct_boundary/main.go --uniprot ENL_HUMAN --min-length 50 --max-length 150
```

### Analyze custom sequence

```bash
go run cmd/construct_boundary/main.go --sequence "MVLSPADKTN..." --name MyProtein
```

### Export for downstream processing

```bash
go run cmd/construct_boundary/main.go --uniprot DOT1L_HUMAN --json > dot1l_boundaries.json
```

## Typical Workflow

1. **Initial scan**: Run with just `--uniprot` to see all suggestions
2. **Refine**: Use `--region` to focus on domain of interest
3. **Constrain**: Add `--min-length`/`--max-length` based on expression system
4. **Design primers**: Use top predictions with `/primerdesigner` skill

## Limitations

- pLDDT-based disorder detection (IUPred not integrated)
- Secondary structure from UniProt annotations only (PSIPRED not integrated)
- No coiled-coil or transmembrane prediction
- Requires network access for UniProt/AlphaFold queries (uses cache)

## Building

```bash
cd benchaid
go build -o cmd/construct_boundary/construct_boundary cmd/construct_boundary/main.go
```
