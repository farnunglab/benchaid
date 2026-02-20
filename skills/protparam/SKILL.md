---
name: protparam
description: Calculate protein parameters (MW, pI, extinction coefficient) and generate purification recommendations. Use when the user asks about protein properties, molecular weight, isoelectric point, extinction coefficients, or purification strategies.
allowed-tools: Bash(protparam_cli:*), Bash(Protparam:*), Bash(python:*)
---

# Protein Parameters Calculator

Calculate protein biophysical parameters and generate purification recommendations.

## CLI Usage

Use the CLI at `scripts/protparam_cli.py`:

### Basic Usage
```bash
scripts/protparam_cli.py --sequence MKTAYIAKQRQISFVKSH...
```

### With Purification Recommendations
```bash
scripts/protparam_cli.py --sequence MKTAYIAKQRQISFVKSH... --purification
```

### JSON Output
```bash
scripts/protparam_cli.py --sequence MKTAYIAKQRQISFVKSH... --json
```

## Options
- `--sequence, -s`: Amino acid sequence in single letter code (required)
- `--purification, -p`: Include purification recommendations
- `--json`: Output results as JSON

## Parameters Calculated

1. **Basic Properties**
   - Sequence length (amino acids)
   - Molecular weight (Da)
   - Theoretical isoelectric point (pI)

2. **Spectroscopic Properties**
   - Molar extinction coefficient at 280nm (M-1cm-1)
   - Absorbance 0.1% (1 g/L)

3. **Tag Detection**
   - His6 tag
   - MBP (Maltose Binding Protein)
   - GST (Glutathione S-Transferase)
   - SUMO tag

4. **Cleavage Site Detection**
   - TEV protease (ENLYFQ/S)
   - 3C/PreScission protease (LEVLFQ/GP)
   - Thrombin (LVPR/GS)
   - SUMO protease (Ulp1)

## Purification Recommendations

When `--purification` is enabled, provides recommendations for:
- Affinity chromatography column (HisTrap, Amylose, GSTrap)
- Tag cleavage strategy
- Ion exchange column (Q or S based on pI)
- Concentrator MWCO
- Size exclusion column (S75, S200, Superose 6)
