# Complex Formation Skill

Guidelines for assembling and purifying macromolecular complexes for structural biology.

## Gel Filtration (Size Exclusion Chromatography)

### Standard Setup

| Parameter | Value |
|-----------|-------|
| Column | Superose 6 Increase 3.2/300 |
| System | ÄKTA micro |
| Fraction size | 0.05 mL (50 µL) |
| Void volume | B6 |

### Elution Positions by Complex Size

| Complex | Expected Fractions | Notes |
|---------|-------------------|-------|
| Large EC* (full elongation complex) | B4-B5 | DSIF, SPT6, PAF1c, etc. |
| EC* + nucleosome | B5-B6 | May approach void |
| Minimal EC (Pol II + DSIF) | B5-C3 | Intermediate |
| Pol II only | C4-C6 | ~500 kDa reference |

**Rule:** If complex elutes earlier than expected → possible aggregation. If later → incomplete assembly or dissociation.

### A260/A280 Ratio Guidelines

| Complex Type | Expected Ratio | Interpretation |
|--------------|----------------|----------------|
| EC* on linear DNA | A280 > A260 | Protein dominates signal |
| Nucleosome-containing | A260 >> A280 | Nucleosomal DNA dominates |

**Red flags:**
- A260/A280 inverted from expectation → wrong complex or contamination
- Very high A260 → free nucleic acid contamination

## Concentration Targets

| Application | Target Range | Minimum |
|-------------|--------------|---------|
| Cryo-EM grids | 100-200 nM | 60 nM |
| Transcription elongation assays | 100-200 nM | 60 nM |

**Below 60 nM:** Not usable — concentration too low for downstream applications.

## Quality Control Checkpoints

### 1. GF Trace Analysis
- Check elution volume matches expected MW
- Verify A260/A280 ratio is appropriate for complex type
- Look for symmetric peak (asymmetry suggests heterogeneity)

### 2. SDS-PAGE
- **Always run SDS-PAGE on fractions before proceeding**
- Check for:
  - All expected subunits present
  - Correct stoichiometry (band intensities)
  - No unexpected bands (contamination/degradation)
  - No missing subunits (incomplete assembly)

### 3. Fraction Selection
- Use **single fractions** (do not pool)
- Selected fractions get cross-linked before grid preparation

## Complex Assembly Workflow

1. **Prepare components** — Query LabBook for current stock concentrations
2. **Calculate recipe** — Use `complex_cli.py` with appropriate preset
3. **Mix components** — Follow stoichiometry from preset (typically 1.5× excess over Pol II)
4. **Incubate** — Allow complex formation (timing depends on complex)
5. **GF purification** — Superose 6 Increase 3.2/300
6. **Analyze fractions** — Check trace + run SDS-PAGE
7. **Select fraction** — Based on elution position, A260/A280, gel appearance
8. **Cross-link** — If proceeding to cryo-EM
9. **Grid preparation** — At 100-200 nM

## CLI Tools

```bash
# List available presets
python3 scripts/complex_cli.py list

# Calculate recipe for EC*
python3 scripts/complex_cli.py ec_star --pol2 5.2uM --volume 100

# Calculate TC-NER complex
python3 scripts/complex_cli.py tc_ner --pol2 5.2uM --volume 100
```

## Troubleshooting

| Problem | Possible Cause | Solution |
|---------|----------------|----------|
| Elutes at void (B6) | Aggregation | Reduce concentration, add salt, check buffer |
| Elutes later than expected | Incomplete assembly | Check component activity, increase incubation |
| Missing bands on gel | Component limiting | Verify stock concentrations, check stoichiometry |
| Extra bands on gel | Contamination/degradation | Check protein quality, use fresh stocks |
| Low A280 signal | Low yield | Scale up input, optimize assembly conditions |

## Empirical Knowledge

Column calibration is empirical — based on previous runs with known complexes. No formal MW standards are used; positions are learned from experience.

---

*Last updated: 2026-01-17*
