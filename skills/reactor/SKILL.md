---
name: reactor
description: Calculate reaction buffer recipes accounting for protein stock contributions. Use when the user asks about designing reaction buffers, calculating buffer volumes, compensation buffers, or setting up biochemistry experiments with proteins.
allowed_commands:
  - "Bash(scripts/reactor_cli.py --list-presets)"
  - "Bash(scripts/reactor_cli.py --list-stocks)"
  - "Bash(scripts/reactor_cli.py:*)"
---

# Reactor - Buffer Calculator

A CLI tool for calculating reaction buffer recipes that account for buffer components contributed by protein stocks.

## Tool Location

`scripts/reactor_cli.py`

## Usage

```bash
# List available presets
python3 scripts/reactor_cli.py --list-presets

# List predefined stock concentrations
python3 scripts/reactor_cli.py --list-stocks

# Calculate using presets
python3 scripts/reactor_cli.py \
    --protein-preset kinase_panel \
    --buffer-preset kinase_assay \
    --volume 100

# Calculate with direct specifications (concentration)
python3 scripts/reactor_cli.py \
    --protein "CDK2:50nM:stock=10uM:buffer=HEPES/20mM,NaCl/150mM" \
    --buffer "HEPES:1M->25mM" \
    --buffer "NaCl:5M->100mM" \
    --volume 100

# Calculate using pmol amounts (auto-converted to concentration)
python3 scripts/reactor_cli.py \
    --protein "PolII:70pmol:stock=5.17uM:buffer=HEPES/20mM,NaCl/150mM" \
    --buffer "HEPES:1M->20mM" \
    --volume 100

# Calculate using molar ratios with reference
python3 scripts/reactor_cli.py \
    --reference 70pmol \
    --protein "PolII:1x:stock=5.17uM:buffer=HEPES/20mM" \
    --protein "DSIF:1.5x:stock=50.8uM:buffer=HEPES/20mM" \
    --buffer "HEPES:1M->20mM" \
    --volume 100

# Use compensation buffer mode (creates concentrated buffer)
python3 scripts/reactor_cli.py \
    --protein "MyProtein:100nM:stock=5uM:buffer=HEPES/20mM,NaCl/300mM" \
    --buffer "HEPES:1M->25mM" \
    --buffer "NaCl:5M->150mM" \
    --volume 50 \
    --mode compensation \
    --fold 10

# Output as JSON
python3 scripts/reactor_cli.py \
    --protein-preset kinase_panel \
    --buffer-preset storage \
    --volume 100 \
    --json
```

## Key Concepts

### Calculation Modes

1. **Direct Mode** (default): Calculates exact volumes of each buffer component to add, accounting for contributions from protein stocks.

2. **Compensation Mode**: Creates a concentrated buffer (e.g., 10X) that compensates for buffer components in protein stocks. Useful for preparing batch buffers.

### Protein Specification Format

```
"Name:Amount:stock=StockConc[:buffer=Component/Conc,Component/Conc,...]"
```

Amount can be specified as:
- **Concentration**: `50nM`, `1uM`, `100mM`
- **Absolute amount**: `70pmol`, `100fmol`, `1nmol` (auto-converted to concentration based on volume)
- **Molar ratio**: `1.5x`, `2x` (requires `--reference` flag)

Examples:
- `"CDK2:50nM:stock=10uM"` - Simple protein without buffer info
- `"CDK2:50nM:stock=10uM:buffer=HEPES/20mM,NaCl/150mM"` - Protein with storage buffer components
- `"PolII:70pmol:stock=5.17uM:buffer=HEPES/20mM"` - Using absolute pmol amount
- `"DSIF:1.5x:stock=50.8uM:buffer=HEPES/20mM"` - Using molar ratio (with `--reference 70pmol`)

### Buffer Component Format

```
"Name:StockConc->FinalConc"
```

Examples:
- `"HEPES:1M->25mM"` - HEPES from 1M stock to 25mM final
- `"NaCl:5M->150mM"` - NaCl from 5M stock to 150mM final
- `"Glycerol:100%->10%"` - Glycerol from 100% to 10% final

### Available Presets

**Protein Presets (built-in):**
- `kinase_panel` - CDK2 and MEK1 for kinase assays
- `purification_stocks` - His-tagged protein and TEV protease
- `reconstitution` - Nucleosome reconstitution
- `polii_elongation_complex` - Pol II elongation complex (PolII, DSIF, IWS1, ELOF1, SPT6, PAF1c, P-TEFb, CSB, DNA-RNA, ntDNA)

**Buffer Presets (built-in):**
- `lysis` - Cell lysis buffer (50mM HEPES, 300mM NaCl, 1mM TCEP, 5% glycerol)
- `gel_filtration` - SEC buffer (25mM Tris, 150mM NaCl, 1mM EDTA, 10% glycerol)
- `storage` - Protein storage buffer (20mM HEPES, 150mM NaCl, 0.5mM TCEP, 10% glycerol)
- `kinase_assay` - Kinase reaction buffer (25mM HEPES, 100mM NaCl, 10mM MgCl2, 1mM DTT, 1mM ATP)
- `cryo_em` - Cryo-EM buffer (20mM HEPES, 150mM NaCl, 1mM TCEP)
- `elongation_buffer` - Elongation assay buffer (20mM HEPES, 75mM NaCl, 10% glycerol, 1mM TCEP, 1mM ATP, 3mM MgCl2)

### External Preset Files

Presets can be loaded from external YAML or JSON files using `--presets-file`. Default locations searched:
- `~/.config/reactor/presets.yaml`

### Predefined Stocks

Common laboratory stock concentrations are predefined:
- HEPES: 1M
- NaCl: 5M
- TCEP: 200mM
- Glycerol: 100%
- MgCl2: 1M
- DTT: 1M
- ATP/GTP: 100mM
- And more (use `--list-stocks` to see all)

## Units Supported

- **Concentration**: M, mM, uM, nM, %, mg/ml
- **Absolute amount**: pmol, fmol, nmol (converted to concentration based on volume)
- **Ratio**: x (e.g., 1.5x, 2x - requires `--reference`)
- **Volume**: uL (microliters)
