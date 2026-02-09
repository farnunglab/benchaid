# TOOLS.md - User Tool Notes (editable)

This file is for *your* notes about external tools and conventions.
It does not define which tools exist.


---

## Cloning

**Quick reference from `skills/cloning/SKILL.md`**

| Criteria | System |
|----------|--------|
| >85 kDa or multi-subunit | Insect (438 series) |
| Small / known E. coli expresser | E. coli (Series 1) |

- **Method:** LIC first → Gibson (NEB HiFi) if fails
- **Source:** Gene synthesis preferred, always codon optimize (IDT tool)
- **Tag:** N-terminal default; C-terminal if N-term buried/functional
- **Multi-subunit:** biGBac (up to 5 per pBig1)
- **QC:** Plasmidsaurus → 100% identity → LabBook registry

```bash
python3 scripts/primer_cli.py lic --sequence ATGXXX... --tag v1
python3 scripts/codon_optimize_cli.py --sequence ATGXXX... --organism insect
```

---

## Insect Cell Expression

**Quick reference from `skills/insect-cell/SKILL.md`**

| Cell Line | Use |
|-----------|-----|
| Sf9 | Transfection, V0/V1 |
| Sf21 | V1, expression |
| Hi5 | Large-scale |

**Key points:**
- Electroporate bacmid DNA in **water** (not EB) — salt causes arcing
- Bacmid isolation: alkaline lysis only, **no kits** (shears DNA)
- Transfection: X-tremeGene 9 in ESF Transfection Medium
- V1 stable ~1-1.5 years at 4°C
- Large-scale: 300-600 mL
