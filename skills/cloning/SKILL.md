# Cloning Skill

Decision tree and workflows for molecular cloning in structural biology labs.

## Expression System Selection

| Criteria | System | Vector Series |
|----------|--------|---------------|
| Multi-subunit complexes | Insect cells | 438 series |
| Large proteins (>85 kDa) | Insect cells | 438 series |
| Known E. coli expressers | E. coli | Series 1 |
| Small proteins / domains | E. coli | Series 1 |

**Default assumption:** If unsure, larger/complex proteins go to insect cells.

**For baculovirus/insect cell expression workflow, see:** `skills/insect-cell/SKILL.md`

## Cloning Method Selection

```
Start
  │
  ├─► Try LIC first (default for 438 and Series 1 vectors)
  │     │
  │     ├─► Success → proceed
  │     │
  │     └─► Failed → use NEB HiFi DNA Assembly (Gibson)
  │
  └─► CPEC: largely replaced, rarely used now
```

**LIC is the default.** Only switch to Gibson (NEB HiFi) if LIC fails.

## Insert Source

| Situation | Approach |
|-----------|----------|
| Plasmid with ORF exists | PCR amplify |
| No existing template | Gene synthesis (Twist) |

**Gene synthesis is now preferred** over classic cloning for new constructs.

### Codon Optimization

- **Always codon optimize** for the target expression system
- **Tool:** IDT Codon Optimization Tool
- Optimize for E. coli or insect cells depending on expression system
- Use `codon_optimize_cli.py` for batch processing

## Tag Strategy

### Default
- **N-terminal His6-MBP-TEV** (cleaved during purification)
- LIC tag version: v1 (no ATG in ORF)

### When to Deviate

| Condition | Tag Position |
|-----------|--------------|
| N-terminus buried (structure/AlphaFold) | C-terminal |
| N-terminus involved in binding | C-terminal |
| Literature precedent suggests otherwise | Follow literature |

**Always check:** AlphaFold prediction or existing structures before deciding tag position.

## Multi-Subunit Complexes (biGBac)

**Always use biGBac** for multi-subunit complexes. Goal: all subunits in one plasmid.

### Capacity

| Vector | Max Subunits |
|--------|--------------|
| pBig1 | 5 subunits |
| pBig2 | 5 × pBig1 = up to 25 subunits |

### Assembly Strategy

1. Clone individual subunits into 438 acceptor vectors (LIC)
2. Combine up to 5 into pBig1 (Gibson assembly)
3. If needed, combine pBig1s into pBig2
4. Alternatively: split across two plasmids and **co-infect** (validated approach, works for multiple projects)

### biGBac Gibson Assembly Protocol

1. PCR amplify each insert (3× 50 µL reactions per insert)
2. Gel purify all PCRs on single column
3. Calculate amounts using **BigBacAssembler** (Notion tool)
4. Mix in 10 µL total:
   - 100 ng SwaI-digested pBig1 vector (or 50 ng minimum)
   - 3-5× molar excess of each insert
   - Limit gel-extracted DNA to 5 µL per 20 µL reaction
5. Add 10 µL 2× Gibson assembly master mix (NEB HiFi)
6. Incubate 50°C for 1 hour
7. Transform entire reaction → plate on LB-spectinomycin

**Tips:**
- 3× insert excess sufficient (per Seychelle)
- 50 ng vector also works
- Promega Wizard Kit gives higher yields for gel extraction

## LIC Protocol Specifics

| Parameter | Value |
|-----------|-------|
| Insert size limit | None (any size works) |
| T4 polymerase treatment | 22°C for 30 min, then 75°C for 20 min |
| Vector versions | v1 (N-term tag), v2 (untagged), v3 (C-term tag) |

### LIC Reaction Setup

**Vector treatment (dGTP):**
| Component | Volume |
|-----------|--------|
| Gel-purified linearized vector (150 ng) | 10 µL |
| 25 mM dGTP stock | 2 µL |
| T4 DNA pol 10× buffer | 2 µL |
| 100 mM DTT | 1 µL |
| T4 DNA polymerase | 0.4 µL |
| H₂O | 4.6 µL |

**Insert treatment (dCTP):**
| Component | Volume |
|-----------|--------|
| Gel-purified PCR (150 ng) | 10 µL |
| 25 mM dCTP stock | 2 µL |
| T4 DNA pol 10× buffer | 2 µL |
| 100 mM DTT | 1 µL |
| T4 DNA polymerase | 0.4 µL |
| H₂O | 4.6 µL |

**Annealing:** 2 µL LICed PCR + 2 µL LICed vector, RT for 10 min

**Transformation:** 2.5 µL annealed product → 100 µL DH5α, heat shock 42°C/45s

### LIC Overhangs (MacroLab)

| Tag | Forward | Reverse |
|-----|---------|---------|
| v1 (N-term) | `TACTTCCAATCCAATGCA` | `TTATCCACTTCCAATGTTATTA` |
| v2 (untagged) | `TTTAAGAAGGAGATATAGATC` | `TTATGGAGTTGGGATCTTATTA` |
| v3 (C-term) | `TTTAAGAAGGAGATATAGTTC` | `GGATTGGAAGTAGAGGTTCTC` |

## Quality Control

### Sequencing
- **Plasmidsaurus** (nanopore long-read) for all clones
- Covers entire plasmid in one read

### Verification Criteria
- **100% identity to reference = PASS**
- Anything less = FAIL (no exceptions for "minor" variants)

### Workflow
1. Pick colonies → grow overnight
2. Miniprep
3. Submit to Plasmidsaurus
4. Analyze with `orf_verifier_cli.py` or `plasmidsaurus_cli.py`
5. **100% correct → Add to LabBook registry**

## CLI Tools

```bash
# Design LIC primers
python3 scripts/primer_cli.py lic --sequence ATGXXX... --tag v1

# Codon optimize for insect cells
python3 scripts/codon_optimize_cli.py --sequence ATGXXX... --organism insect

# Analyze Plasmidsaurus results
python3 scripts/plasmidsaurus_cli.py analyze /path/to/results/

# Verify ORF against reference
python3 scripts/orf_verifier_cli.py --input clone.gb --reference uniprot_id

# biGBac assembly calculator (from Notion)
python3 big_bac_assembler_Notion.py
```

## Protocol References

| Protocol | File |
|----------|------|
| LIC | `protocols/Ligation-Independent Cloning (LIC) (prt_tOYB7mRe).md` |
| biGBac | `protocols/BigBac Cloning (prt_atebFqGl).md` |
| biGBac tips | `protocols/BigBac (additional advice from Seychelle, February 2020) (prt_7eqRkXm0).md` |

## Notion Resources

- **BigBac Assembler:** Tool for calculating Gibson assembly amounts
- **LIC vectors database:** `<YOUR_NOTION_DB_ID>`
- **Series-438 database:** `<YOUR_NOTION_DB_ID>`

## Related Skills

- **Insect cell expression:** `skills/insect-cell/SKILL.md` — baculovirus, transfection, V0/V1, large-scale

## Common Failure Modes

| Problem | Likely Cause | Solution |
|---------|--------------|----------|
| No colonies | Ligation failed, incompetent cells | Check LIC reaction, use fresh competent cells |
| Wrong size insert | Mispriming, template contamination | Gel purify PCR product, check primers |
| Mutations in sequence | PCR errors | Use high-fidelity polymerase, reduce cycles |
| Incomplete assembly (biGBac) | Too many fragments | Split into fewer fragments, optimize ratios |

## Workflow Summary

```
1. Decide expression system (size/complexity → insect vs E. coli)
2. Design construct (check tag position with AlphaFold)
3. Get insert (PCR from plasmid OR gene synthesis + codon optimize)
4. Clone (LIC first, Gibson if LIC fails)
5. For multi-subunit: biGBac assembly
6. Sequence (Plasmidsaurus)
7. Verify 100% identity
8. Register in LabBook
```

---

*Last updated: 2026-01-17*
