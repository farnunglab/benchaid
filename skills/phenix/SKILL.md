---
name: phenix
description: PHENIX suite for macromolecular structure determination. Use for cryo-EM model building, real-space refinement, map analysis, validation, and AlphaFold model processing.
---

# PHENIX - Macromolecular Structure Determination

PHENIX (Python-based Hierarchical ENvironment for Integrated Xtallography) is a comprehensive suite for structure determination via X-ray crystallography, cryo-EM, and neutron diffraction.

## Installation

PHENIX requires a license (free for academics). Download from: https://www.phenix-online.org/

After installation, source the environment:
```bash
source /path/to/phenix-1.21/phenix_env.sh
```

## Documentation
- Main: https://www.phenix-online.org/documentation/
- Cryo-EM: https://www.phenix-online.org/documentation/overviews/cryo-em_index.html
- AlphaFold models: https://www.phenix-online.org/documentation/reference/alphafold.html

---

## Cryo-EM Workflow Overview

```
Map → Mtriage (assess quality)
     ↓
Auto-sharpen / Resolve (improve map)
     ↓
Dock AlphaFold model OR Map-to-model (build)
     ↓
Real-space refine
     ↓
Validation
```

---

## Core Commands

### 1. Map Quality Assessment (mtriage)

Evaluate map resolution, FSC, and statistics.

```bash
# Basic map statistics
phenix.mtriage map.mrc

# With half-maps (calculates d_FSC)
phenix.mtriage map.mrc half_map_1.mrc half_map_2.mrc

# With model (calculates d_model, FSC_model)
phenix.mtriage map.mrc model.pdb

# Full analysis
phenix.mtriage map.mrc model.pdb half_map_1.mrc half_map_2.mrc nproc=8
```

**Key resolution estimates:**
| Metric | Meaning |
|--------|---------|
| d_FSC | Resolution from half-map FSC at 0.143 |
| d99 | Resolution cutoff where Fourier coefficients become negligible |
| d_model | Resolution where model map best matches experimental map |
| d_FSC_model | Resolution where model and map Fourier coefficients diverge |

---

### 2. Map Sharpening (auto_sharpen)

Optimize map interpretability by adjusting B-factor.

```bash
# Basic auto-sharpening
phenix.auto_sharpen map.mrc resolution=3.2

# With model for better masking
phenix.auto_sharpen map.mrc model.pdb resolution=3.2

# With half-maps (uses FSC for local sharpening)
phenix.auto_sharpen map.mrc half_map_1.mrc half_map_2.mrc resolution=3.2

# Output options
phenix.auto_sharpen map.mrc resolution=3.2 output_file=sharpened_map.mrc
```

---

### 3. Map Density Modification (resolve_cryo_em)

Improve map by density modification (reduces noise, improves connectivity).

```bash
phenix.resolve_cryo_em map.mrc resolution=3.2

# With sequence for better results
phenix.resolve_cryo_em map.mrc resolution=3.2 seq_file=sequence.fasta

# With half-maps
phenix.resolve_cryo_em map.mrc half_map_1.mrc half_map_2.mrc resolution=3.2
```

---

### 4. Process AlphaFold Models

Prepare predicted models for use in cryo-EM.

```bash
# Remove low-confidence regions, convert pLDDT to B-factors
phenix.process_predicted_model model.pdb

# With pLDDT cutoff (remove residues below threshold)
phenix.process_predicted_model model.pdb pae_file=pae.json \
    remove_low_confidence_residues=True \
    minimum_plddt=70

# Split into domains
phenix.process_predicted_model model.pdb pae_file=pae.json split_model_by_domains=True
```

---

### 5. Dock Model into Map

#### dock_in_map (rigid-body docking)
```bash
# Dock one chain
phenix.dock_in_map map.mrc model.pdb resolution=3.2

# Multiple chains/copies
phenix.dock_in_map map.mrc chain_a.pdb chain_b.pdb resolution=3.2 \
    search_copies=2

# With sequence
phenix.dock_in_map map.mrc model.pdb seq_file=sequence.fasta resolution=3.2
```

#### dock_predicted_model (for AlphaFold models)
```bash
phenix.dock_predicted_model map.mrc model.pdb resolution=3.2
```

#### dock_and_rebuild (dock + local rebuilding)
```bash
phenix.dock_and_rebuild map.mrc model.pdb resolution=3.2 nproc=8
```

---

### 6. Model Building

#### PredictAndBuild (AlphaFold-assisted, recommended)
```bash
# Builds model using AlphaFold predictions
phenix.predict_and_build map.mrc seq_file=sequence.fasta resolution=3.2 nproc=8
```

#### map_to_model (de novo)
```bash
phenix.map_to_model map.mrc resolution=3.2 seq_file=sequence.fasta nproc=8
```

#### trace_and_build (rapid backbone tracing)
```bash
phenix.trace_and_build map.mrc resolution=3.2 seq_file=sequence.fasta
```

---

### 7. Real-Space Refinement

The workhorse for refining models against cryo-EM maps.

```bash
# Basic refinement (5 macro-cycles by default)
phenix.real_space_refine model.pdb map.mrc resolution=3.2

# Use multiple processors for B-factor refinement
phenix.real_space_refine model.pdb map.mrc resolution=3.2 nproc=8

# More macro-cycles for poor starting model
phenix.real_space_refine model.pdb map.mrc resolution=3.2 macro_cycles=10

# With ligand restraints
phenix.real_space_refine model.pdb map.mrc ligand.cif resolution=3.2
```

#### Refinement Strategies

```bash
# Default: minimization + local grid search + ADP refinement
phenix.real_space_refine model.pdb map.mrc resolution=3.2

# Add morphing (good for initial fitting)
phenix.real_space_refine model.pdb map.mrc resolution=3.2 \
    run=minimization_global+local_grid_search+morphing+adp

# Add simulated annealing (escape local minima)
phenix.real_space_refine model.pdb map.mrc resolution=3.2 \
    run=minimization_global+local_grid_search+morphing+simulated_annealing+adp

# Rigid body only
phenix.real_space_refine model.pdb map.mrc resolution=3.2 run=rigid_body \
    rigid.eff  # file defining rigid groups
```

#### Geometry Targets
```bash
# Stricter geometry (for high-resolution)
phenix.real_space_refine model.pdb map.mrc resolution=2.5 \
    target_bonds_rmsd=0.01 target_angles_rmsd=1.0

# Looser geometry (for low-resolution)
phenix.real_space_refine model.pdb map.mrc resolution=4.5 \
    target_bonds_rmsd=0.02 target_angles_rmsd=2.0
```

#### Secondary Structure Restraints
```bash
phenix.real_space_refine model.pdb map.mrc resolution=3.2 \
    secondary_structure.enabled=True
```

#### NCS Constraints
```bash
# Auto-detect NCS (default)
phenix.real_space_refine model.pdb map.mrc resolution=3.2 ncs_constraints=True

# Disable NCS
phenix.real_space_refine model.pdb map.mrc resolution=3.2 ncs_constraints=False

# Manual NCS definition
phenix.real_space_refine model.pdb map.mrc resolution=3.2 ncs.eff
```

#### Reference Model Restraints
```bash
phenix.real_space_refine model.pdb map.mrc resolution=3.2 \
    reference_model.enabled=True \
    reference_model.file=high_res_model.pdb
```

---

### 8. Validation

```bash
# Model vs map validation
phenix.model_vs_data model.pdb map.mrc resolution=3.2

# Get validation report (for deposition)
phenix.validation_cryoem model.pdb map.mrc resolution=3.2 \
    half_map_1.mrc half_map_2.mrc

# MolProbity-style validation
phenix.molprobity model.pdb
```

---

### 9. Map Utilities

#### map_box (extract region)
```bash
# Extract box around model
phenix.map_box map.mrc model.pdb

# Specific selection
phenix.map_box map.mrc model.pdb selection="chain A"

# Keep original origin
phenix.map_box map.mrc model.pdb keep_origin=True
```

#### combine_focused_maps
```bash
phenix.combine_focused_maps map1.mrc map2.mrc map3.mrc \
    model.pdb resolution=3.2
```

#### map_symmetry
```bash
# Find symmetry in map
phenix.map_symmetry map.mrc

# Apply symmetry
phenix.map_symmetry map.mrc symmetry=D2
```

---

### 10. Model Utilities

#### superpose_pdbs
```bash
phenix.superpose_pdbs fixed=reference.pdb moving=model.pdb
```

#### pdbtools
```bash
# Renumber chains
phenix.pdbtools model.pdb rename_chain_id.old_id=A rename_chain_id.new_id=B

# Remove waters
phenix.pdbtools model.pdb remove="water"

# Remove hydrogens
phenix.pdbtools model.pdb remove="element H"

# Reset B-factors
phenix.pdbtools model.pdb set_b_iso=50
```

#### geometry_minimization
```bash
# Idealize geometry without map
phenix.geometry_minimization model.pdb
```

---

### 11. Ligand Tools

#### eLBOW (generate restraints)
```bash
# From SMILES
phenix.elbow --smiles="CCO" --id=ETH

# From PDB ligand
phenix.elbow --chemical_id=ATP

# From molecule file
phenix.elbow ligand.mol2
```

#### LigandFit
```bash
phenix.ligandfit map.mrc model.pdb ligand.pdb resolution=3.2
```

---

### 12. Water Building (douse)

```bash
phenix.douse map.mrc model.pdb resolution=3.2

# Stricter peak height cutoff
phenix.douse map.mrc model.pdb resolution=3.2 peak_cutoff=3.0
```

---

## Common Parameter Files

### NCS Groups (ncs.eff)
```
pdb_interpretation {
  ncs_group {
    reference = chain A
    selection = chain B
  }
  ncs_group {
    reference = chain C
    selection = chain D
    selection = chain E
  }
}
```

### Rigid Body Groups (rigid.eff)
```
refinement.rigid_body {
  group = chain A
  group = chain B or chain C
  group = chain D and resseq 1:100
}
```

### Custom Geometry Restraints (edits.eff)
```
geometry_restraints {
  edits {
    bond {
      atom_selection_1 = chain A and resseq 123 and name SG
      atom_selection_2 = chain B and resseq 456 and name SG
      distance_ideal = 2.03
      sigma = 0.02
    }
  }
}
```

---

## Atom Selection Syntax

PHENIX uses a powerful selection syntax:

```
chain A                          # All atoms in chain A
chain A and resseq 1:100         # Residues 1-100 in chain A
resname ALA                      # All alanines
name CA                          # All CA atoms
chain A and name CA              # CA atoms in chain A
element Fe                       # All iron atoms
water                            # All waters
not water                        # Everything except water
chain A or chain B               # Chains A and B
(chain A and resseq 50) around 5 # Within 5Å of residue 50 in chain A
```

---

## Tips

1. **Resolution is required** for CCP4/MRC maps - PHENIX cannot determine it automatically

2. **Always run mtriage first** to assess map quality and get accurate resolution

3. **Use nproc** for parallel processing (especially for ADP refinement)

4. **Start with default refinement**, then add morphing/SA if needed

5. **For AlphaFold models**: use `process_predicted_model` first, then `dock_predicted_model`

6. **Check validation** between refinement rounds to track improvements

7. **Model format**: PHENIX accepts both PDB and mmCIF; use mmCIF for large structures

---

## Citation

```
Macromolecular structure determination using X-rays, neutrons and electrons: 
recent developments in Phenix. D. Liebschner et al. Acta Cryst. (2019). D75, 861-877
```
