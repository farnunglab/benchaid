---
name: primerdesigner
description: Design PCR primers for molecular cloning. Use when the user asks about designing primers, LIC cloning primers, sequencing primers, Gibson assembly primers, or working with NCBI accession codes for cloning.
allowed-tools: Bash(primer_cli:*), Bash(primerdesigner:*), Bash(python:*)
---

# Primer Designer Tool

Design PCR primers for LIC cloning, sequencing, and Gibson/HiFi assembly using Primer3.

## CLI Location

```bash
scripts/primer_cli.py
```

## Quick Start

### LIC Cloning Primers (default v1)
```bash
python3 scripts/primer_cli.py --index 1 --accession NM_007192
```

### LIC Cloning with Specific Tag Version
```bash
python3 scripts/primer_cli.py --index 1 --accession NM_007192 --lic-tag v2
```

### Gibson/HiFi Assembly Primers
```bash
python3 scripts/primer_cli.py --index 1 --accession NM_007192 --hifi --vector 438-A
```

### List Available Options
```bash
python3 scripts/primer_cli.py --list-lic-tags
python3 scripts/primer_cli.py --list-vectors
```

## Options

| Option | Description |
|--------|-------------|
| `--index, -i` | Starting index number for primer naming (required) |
| `--accession, -a` | NCBI accession code (NM_ or XM_ prefix) |
| `--sequence, -s` | Raw DNA sequence (ATCG only) |
| `--gene, -g` | Gene name (required with --sequence) |
| `--lic-tag, -t` | LIC tag version: v1, v2, v3, vKoz, vBac, vGFP1, vGFP2, vHRV |
| `--list-lic-tags` | List available LIC tag versions and exit |
| `--hifi, --gibson` | Design HiFi/Gibson assembly primers |
| `--vector, -v` | Vector name (e.g., 438-A) - also auto-selects LIC tag |
| `--overlap-tm` | Target Tm for overlap regions (default: 60°C) |
| `--list-vectors` | List available vectors and exit |
| `--lic-only` | Only generate LIC cloning primers |
| `--seq-only` | Only generate sequencing primers |
| `--json` | Output results as JSON |

## LIC Tag Versions (MacroLab Vectors v8)

| Tag | Forward Overhang | Reverse Overhang | ORF Requirement |
|-----|------------------|------------------|-----------------|
| **v1** | `TACTTCCAATCCAATGCA` | `TTATCCACTTCCAATGTTATTA` | No ATG in ORF |
| **v2** | `TTTAAGAAGGAGATATAGATC` | `TTATGGAGTTGGGATCTTATTA` | ORF needs ATG |
| **v3** | `TTTAAGAAGGAGATATAGTTC` | `GGATTGGAAGTAGAGGTTCTC` | ORF needs ATG |
| **vKoz** | `TACTTCCAATCCAATGCCACC` | `TTATCCACTTCCAATGTTATTA` | ORF needs ATG |
| **vBac** | `TACTTCCAATCCAATCG` | `TTATCCACTTCCAATGTTATTA` | ORF needs ATG |
| **vGFP1** | `TACTTCCAATCCAATGCA` | `CTCCCACTACCAATGCC` | No stop codon |
| **vGFP2** | `TTTAAGAAGGAGATATAGATC` | `GTTGGAGGATGAGAGGATCCC` | ORF needs ATG |
| **vHRV** | `GTGCTGTTCCAGGGTCCGAAT` | `TGGTGGTGGTGGTGCTCGATTA` | HRV 3C SLIC |

### When to Use Each Tag

| Tag | Use Case | Example Vectors |
|-----|----------|-----------------|
| **v1** | N-terminal tagged constructs (His6-MBP, His6-GST, etc.) | 1B, 1C, 1M, 2BT, 2CT, 4B, 4C, 438-B, 438-C |
| **v2** | Untagged expression | 2AT |
| **v3** | C-terminal tagged constructs | 2Bc-T, 2Cc-T, 2Oc-T, 2Tc-T |
| **vKoz** | Eukaryotic expression with Kozak sequence | - |
| **vBac** | Baculovirus/insect cell untagged | 4A, 5A, 438-A |
| **vGFP1** | C-terminal fluorescent protein fusion (N-term tagged) | MBP-mCherry, H6-msfGFP |
| **vGFP2** | C-terminal fluorescent protein fusion (untagged) | u-mCherry, u-msfGFP |
| **vHRV** | HRV 3C protease site SLIC cloning | - |

## Auto-Selection from Vector

When using `--vector`, the appropriate LIC tag is auto-selected:

```bash
# Auto-selects vBac for 438-A (untagged insect)
python3 scripts/primer_cli.py --index 1 --accession NM_007192 --vector 438-A

# Auto-selects v1 for 438-B (His6-MBP)
python3 scripts/primer_cli.py --index 1 --accession NM_007192 --vector 438-B

# Auto-selects v2 for 2AT (untagged E. coli)
python3 scripts/primer_cli.py --index 1 --accession NM_007192 --vector 2AT
```

You can override auto-selection with explicit `--lic-tag`:
```bash
python3 scripts/primer_cli.py --index 1 --accession NM_007192 --vector 438-B --lic-tag v2
```

## Primer Types

### 1. LIC Primers (Ligation Independent Cloning)
Overhangs determined by tag version:
```
LF1_GeneName_LICv1_F    TACTTCCAATCCAATGCA{binding_region}
LF2_GeneName_LICv1_R    TTATCCACTTCCAATGTTATTA{binding_region}
```

### 2. HiFi/Gibson Assembly Primers
Dynamic overlaps calculated to achieve target Tm (default 60°C):
- Forward: [vector upstream overlap] + [gene binding region]
- Reverse: [vector downstream overlap RC] + [gene binding region]

Output includes detailed Tm information:
```
LF1_SUPT16H_HiFi_F    ACACCTCCCCCTGAACCTGATGGCTGTGACTCTGGACAAAGACGCTTAT
  # Overlap: ACACCTCCCCCTGAACCTG (Tm: 61.5°C, 19 bp)
  # Binding: ATGGCTGTGACTCTGGACAAAGACGCTTAT (Tm: 67.8°C)
```

### 3. Sequencing Primers
Spaced ~750bp apart for full-length sequencing coverage.

## Available Vectors

Vectors are loaded from `./vectors/` directory:

| Vector | Tag | LIC Tag | Host |
|--------|-----|---------|------|
| 438-A | - (untagged) | vBac | Insect |
| 438-B | His6-TEV | v1 | Insect |
| 438-C | His6-MBP-TEV | v1 | Insect |
| 438-D | His6-GST-TEV | v1 | Insect |
| 438-G | His6-GB1-TEV | v1 | Insect |

## Examples

### LICv2 for Untagged Expression
```bash
python3 scripts/primer_cli.py --index 1 --sequence ATGCATGC... \
  --gene MyGene --lic-tag v2 --lic-only
```

### LICv3 for C-terminal Tags
```bash
python3 scripts/primer_cli.py --index 1 --accession NM_007192 \
  --lic-tag v3 --lic-only
```

### Gibson/HiFi with Custom Overlap Tm
```bash
python3 scripts/primer_cli.py --index 1 --accession NM_007192 \
  --hifi --vector 438-B --overlap-tm 65
```

### JSON Output for Parsing
```bash
python3 scripts/primer_cli.py --index 1 --accession NM_007192 \
  --lic-only --json
```

## Restriction Site Check

Automatically warns about internal SwaI and PmeI sites that could interfere with cloning.

## Configuration

Settings in `scripts/settings.py`:
- Email: configured in `scripts/settings.py`
- Initials: configured in `scripts/settings.py` (used in primer names)
