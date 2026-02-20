---
name: codon-optimize
description: Codon optimize protein sequences for expression using IDT's API. Use when the user asks to codon optimize genes, sequences, or accessions for a target organism (insect, E. coli, mammalian, yeast) or vector (438, 1-, pVEX).
---

# Codon Optimization (IDT)

Use the Python CLI at `scripts/codon_optimize_cli.py`.

## Environment
The CLI loads credentials from `.env`:
- `IDT_CLIENT_ID`
- `IDT_CLIENT_SECRET`
- `IDT_USERNAME` (IDT account email)
- `IDT_PASSWORD` (IDT account password)

## Examples

### From NCBI Accession
```bash
python3 scripts/codon_optimize_cli.py --accession NP_003161 --organism insect --name SUPT6H
```

### From Raw Protein Sequence
```bash
python3 scripts/codon_optimize_cli.py --sequence MKTLLLTLVVV... --organism ecoli --name MyProtein
```

### Vector Inference (Infers Organism from Vector)
```bash
python3 scripts/codon_optimize_cli.py --accession NP_003161 --vector 438-C
```

### Truncated Construct (Residue Range)
```bash
python3 scripts/codon_optimize_cli.py --accession NP_003161 --residues 1-500 --organism human
```

## Options
| Option | Description |
|--------|-------------|
| `--sequence, -s` | Protein sequence (mutually exclusive with `--accession`) |
| `--accession, -a` | NCBI protein accession (NP_, XP_, etc.) |
| `--residues, -r` | Residue range to extract (e.g., `1-300`) |
| `--name, -n` | Gene/construct name |
| `--organism, -o` | Target organism (see mapping below) |
| `--vector, -v` | Target vector (infers organism) |
| `--json` | Output as JSON |
| `--fasta` | Output as FASTA |
| `--output, -O` | Write to file |

## Organism Mapping
| Input | IDT Organism |
|-------|--------------|
| `insect`, `sf9`, `sf21` | Spodoptera frugiperda |
| `hi5`, `trichoplusia` | Trichoplusia ni |
| `ecoli`, `bacteria` | Escherichia coli K12 |
| `human`, `mammalian`, `hek` | Homo sapiens |
| `cho` | Cricetulus griseus |
| `yeast` | Saccharomyces cerevisiae |
| `pichia` | Pichia pastoris |

## Vector → Organism Inference
| Vector Pattern | Organism |
|----------------|----------|
| `438-*` | insect |
| `1-*` | ecoli |
| `pVEX-*` | human |

## Output
Returns optimized DNA sequence with:
- Length in bp (should be 3× input aa)
- GC content percentage
- Complexity score (if available from IDT)
