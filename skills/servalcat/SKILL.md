---
name: servalcat
description: Servalcat for cryo-EM SPA reciprocal-space refinement and Fo-Fc map calculation. Use for refining models against half-maps, calculating weighted difference maps, and omit maps.
---

# Servalcat - Cryo-EM Reciprocal-Space Refinement

Servalcat (**S**tructur**e** **r**efinement and **val**idation for **c**rystallography and single p**a**r**t**icle analysis) performs reciprocal-space refinement and map calculation for cryo-EM SPA and crystallography.

**Key advantage over real-space refinement:** Produces properly weighted and sharpened Fo-Fc difference maps.

## Installation

Servalcat is included in CCP4 (v9.0+). Alternatively:
```bash
pip install servalcat
```

Source: https://github.com/keitaroyam/servalcat

## Documentation
- Main: https://servalcat.readthedocs.io/
- SPA refinement: https://servalcat.readthedocs.io/en/latest/spa.html
- Examples: https://servalcat.readthedocs.io/en/latest/spa_examples/index.html

---

## Basic Usage

```bash
servalcat <command> <args>

# Get help for any command
servalcat <command> -h
```

---

## Cryo-EM SPA Commands

### 1. Refinement (refine_spa_norefmac)

Reciprocal-space refinement against half-maps with automatic Fo-Fc map calculation.

```bash
# Basic refinement (run in a NEW directory!)
servalcat refine_spa_norefmac \
    --model model.pdb \
    --halfmaps half_map_1.mrc half_map_2.mrc \
    --resolution 3.0 \
    --ncycle 10
```

**Important:** Half-maps must be **unsharpened and unweighted** (e.g., from RELION Refine3D).

#### With Point Group Symmetry
```bash
# C3 symmetry - model is ASU only
servalcat refine_spa_norefmac \
    --model asu_model.pdb \
    --halfmaps half_map_1.mrc half_map_2.mrc \
    --resolution 2.5 \
    --pg C3 \
    --ncycle 10
```

Supported symmetry: Cn, Dn, T, O, I (follows RELION convention - center of box is origin).

#### With Helical Symmetry
```bash
servalcat refine_spa_norefmac \
    --model model.pdb \
    --halfmaps half_map_1.mrc half_map_2.mrc \
    --resolution 3.5 \
    --twist 179.4 --rise 2.4 \
    --ncycle 10
```

#### Common Options

| Option | Description |
|--------|-------------|
| `--resolution` | Resolution limit (use slightly higher than global FSC=0.143) |
| `--ncycle N` | Number of refinement cycles (default: 10) |
| `--mask_for_fofc mask.mrc` | Mask for Fo-Fc map calculation (doesn't affect refinement) |
| `--ligand lig.cif` | Restraint dictionary for ligands |
| `--jellybody` | Enable jelly-body refinement |
| `--weight VALUE` | Override automatic weight determination |
| `--pixel_size VALUE` | Override pixel size from header |
| `--hydrogen {all,yes,no}` | Hydrogen handling (default: all = regenerate) |
| `--hout` | Write hydrogens to output model |
| `-o PREFIX` | Output prefix (default: refined) |
| `--cross_validation` | Use half1 for refinement, half2 for validation |

#### Output Files

| File | Description |
|------|-------------|
| `refined.pdb` | Refined model (PDB format) |
| `refined.mmcif` | Refined model (mmCIF format) |
| `refined_expanded.pdb` | Symmetry-expanded model |
| `refined_diffmap.mtz` | Fo and Fo-Fc maps (auto-opens in Coot) |
| `refined_diffmap_normalized_fofc.mrc` | Normalized Fo-Fc map |
| `refined_fsc.log` | FSC curves (view with `loggraph refined_fsc.log`) |

---

### 2. Fo-Fc Map Calculation (fofc)

Calculate difference maps without refinement (use after refinement or for omit maps).

```bash
# Basic Fo-Fc calculation
servalcat fofc \
    --model refined.pdb \
    --halfmaps half_map_1.mrc half_map_2.mrc \
    --resolution 3.0 \
    --mask mask.mrc \
    -o diffmap
```

#### Omit Map Workflow

1. Refine complete model first
2. Remove atoms to omit (e.g., ligand) in Coot → save as `model_omit.pdb`
3. Calculate omit map:

```bash
servalcat fofc \
    --model model_omit.pdb \
    --halfmaps half_map_1.mrc half_map_2.mrc \
    --resolution 3.0 \
    --mask mask.mrc \
    -o omit_map
```

#### Hydrogen-Omit Map
```bash
servalcat fofc \
    --model refined.pdb \
    --halfmaps half_map_1.mrc half_map_2.mrc \
    --resolution 3.0 \
    --mask mask.mrc \
    --omit_proton \
    -o h_omit
```

---

### 3. Map Trimming (trim)

Reduce map file sizes by removing empty regions.

```bash
servalcat trim \
    --maps postprocess.mrc half_map_1.mrc half_map_2.mrc \
    --mask mask.mrc \
    --padding 10
```

Options:
- `--model model.pdb` — Use model to define boundary (if no mask)
- `--no_shift` — Keep original origin (maps overlap with input)
- `--noncubic` — Don't enforce cubic box
- `--noncentered` — Don't center on original map

---

## Crystallographic Refinement

```bash
servalcat refine_xtal_norefmac \
    --model input.pdb \
    --hklin data.mtz \
    -s xray \
    --ncycle 10
```

Source options: `xray`, `neutron`, `electron`

---

## Utility Commands

### Expand NCS/Symmetry
```bash
# Using Servalcat
servalcat util expand --model model.pdb

# Or using gemmi
gemmi convert --expand-ncs=new model.pdb model_expanded.pdb
```

### Find Fo-Fc Peaks
```bash
servalcat util map_peaks \
    --map refined_diffmap_normalized_fofc.mrc \
    --model refined.pdb \
    --abs_level 4.0
```

### Convert FSC JSON to CSV
```bash
servalcat util json2csv refined_fsc.json
```

---

## External Restraints (Refmac Keywords)

Servalcat supports Refmac-style keyword files for external restraints.

```bash
servalcat refine_spa_norefmac \
    --model model.pdb \
    --halfmaps half_1.mrc half_2.mrc \
    --resolution 3.0 \
    --keyword_file restraints.txt
```

### Example Restraint File
```
# Distance restraint
external distance first chain A resi 50 atom CA \
                  second chain B resi 100 atom CA \
                  value 10.0 sigma 0.5

# Harmonic positional restraint
external harmonic first chain A resi 1:50 sigma 0.1
```

---

## Viewing Maps

### In Coot
```bash
# Auto-generated script opens model + maps correctly
coot --script refined_coot.py
```

**Note:** Ignore "rmsd" sigma levels in Coot for SPA maps. Use raw map values directly (normalized within mask = true sigma).

### In PyMOL
```python
# MUST disable normalization before loading maps!
set normalize_ccp4_maps, off
load refined_diffmap_normalized_fofc.mrc
isomesh mesh_fofc, refined_diffmap_normalized_fofc, 4.0
```

---

## Tips

1. **Always use unsharpened, unweighted half-maps** from RELION Refine3D (not PostProcess)

2. **Resolution:** Set slightly higher than global FSC=0.143 (local resolution may be better)

3. **Run in a new directory** — Servalcat creates many files with fixed names

4. **Check FSC curves** with `loggraph refined_fsc.log` to assess overfitting
   - FSC_model should not exceed FSC_full_sqrt (indicates overfitting)

5. **For omit maps:** Refine complete model first, then remove atoms and recalculate maps

6. **Sigma interpretation:** Maps normalized within mask show true sigma levels; ignore Coot's "rmsd" display

7. **Weight adjustment:** If geometry is too loose/tight, adjust with `--weight` (larger = looser restraints)

---

## Workflow: Complete SPA Structure

```bash
# 1. Create working directory
mkdir refinement && cd refinement

# 2. Initial refinement
servalcat refine_spa_norefmac \
    --model ../initial_model.pdb \
    --halfmaps ../half_map_1.mrc ../half_map_2.mrc \
    --mask_for_fofc ../mask.mrc \
    --resolution 2.8 \
    --ncycle 10

# 3. Check results
coot --script refined_coot.py

# 4. If needed: edit model in Coot, save, re-refine
servalcat refine_spa_norefmac \
    --model refined_edited.pdb \
    --halfmaps ../half_map_1.mrc ../half_map_2.mrc \
    --mask_for_fofc ../mask.mrc \
    --resolution 2.8 \
    --ncycle 5 \
    -o refined_round2

# 5. Validate
molprobity.molprobity refined_expanded.pdb nqh=false

# 6. Calculate omit map for ligand (optional)
servalcat fofc \
    --model refined_no_ligand.pdb \
    --halfmaps ../half_map_1.mrc ../half_map_2.mrc \
    --mask ../mask.mrc \
    --resolution 2.8 \
    -o ligand_omit
```

---

## Citation

**Cryo-EM SPA refinement:**
> Yamashita, K., Palmer, C. M., Burnley, T., Murshudov, G. N. (2021)
> "Cryo-EM single particle structure refinement and map calculation using Servalcat"
> Acta Cryst. D77, 1282-1291

**Refmacat and restraint generation:**
> Yamashita, K., Wojdyr, M., Long, F., Nicholls, R. A., Murshudov, G. N. (2023)
> "GEMMI and Servalcat restrain REFMAC5"
> Acta Cryst. D79, 368-373
