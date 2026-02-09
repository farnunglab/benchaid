# Insect Cell Expression Skill

Baculovirus expression system for recombinant protein production.

## Cell Lines

| Cell Line | Species | Origin | Use |
|-----------|---------|--------|-----|
| Sf9 | *Spodoptera frugiperda* | Fall Army Worm ovary | Transfection, V0/V1 production |
| Sf21 | *Spodoptera frugiperda* | Fall Army Worm ovary | V1 production, expression |
| Hi5 | *Trichoplusia ni* | Cabbage Looper ovary | Large-scale expression |

**Media:** ESF-921 (serum-free, Expression Systems)

All lines can be grown as suspension or adherent cultures.

## Baculovirus System Overview

**Virus:** AcMNPV (Autographa californica multicapsid nucleopolyhedrovirus)
- ~130 kb dsDNA genome
- Cannot infect human cells
- Modified into bacmid for easy gene insertion

**Bacmid host:** DH10αEMBacY
- Contains AcMNPV bacmid + Tn7 transposase helper plasmid
- YFP reporter under PolH promoter (tracks infection)
- Selection: kanamycin (bacmid), tetracycline (helper)

**Vector system:** 438 series (MacroLab, UC Berkeley)
- LIC cloning, multiple tagging options
- Tn7-mediated integration into bacmid
- Gentamycin resistance after integration
- PolH promoter drives expression

## Workflow Overview

```
438 vector with GOI
       ↓
Electroporate into DH10αEMBacY
       ↓
Blue/white selection (gent + X-Gal + IPTG)
       ↓
Isolate bacmid DNA (alkaline lysis)
       ↓
Transfect adherent Sf9 → V0 (2-4 days)
       ↓
Infect suspension Sf9/Sf21 → V1 (DPA + 48-72 hrs)
       ↓
Large-scale expression (300-600 mL Hi5/Sf9/Sf21)
       ↓
Harvest & purify protein
```

## DH10αEMBacY Recombination

### Electroporation

1. Add 0.25-1 µg plasmid to 100 µL electrocompetent DH10αEMBacY
   - **DNA must be in water** (not EB buffer) — salt causes arcing
2. Incubate on ice 10 min
3. Transfer to chilled 0.1 cm cuvette
4. Pulse: **25 µF, 1.8 kV** (E. coli program 1)
   - If "arc" warning → too much salt, use less DNA
5. Add 1 mL LB, transfer to culture tube
6. Shake 5 hrs to overnight at 37°C

### Selection

1. Plate 25-150 µL on LB agar + gentamycin + X-Gal (150 µg/mL) + IPTG (1 mM)
2. Incubate 1.5 days at 37°C
3. Pick **white colonies** (integration disrupts LacZ → white)
   - Blue = no integration (negative control)
4. Streak white colonies on fresh plate (gent + X-Gal + IPTG)
5. Inoculate same colony into 5 mL LB-gent

## Bacmid Isolation

**⚠️ Do NOT use commercial miniprep kits** — they shear the large (~140 kb) bacmid DNA. Bacmid must remain supercoiled for efficient transfection.

### Alkaline Lysis Protocol

1. Pellet entire 5 mL culture
2. Resuspend in 250 µL resuspension buffer
3. Add 250 µL lysis buffer, invert 3-5×
4. Add 350 µL neutralization buffer, invert 3-5×
5. Spin 15,000×g for 10 min at RT
6. Transfer supernatant to fresh tube
7. Spin again 15,000×g for 10 min (remove remaining precipitate)
8. Add 700 µL isopropanol (-20°C or RT)
9. Invert 3-5×, incubate at -20°C for 1 hr (or -80°C for 1-2 hrs)
10. Spin 15,000×g for 30 min at 4°C
11. Remove supernatant carefully
12. Wash with 500 µL 70% EtOH
13. Spin 15,000×g for 10 min at 4°C
14. Remove EtOH, add 30 µL 70% EtOH to cover pellet
15. Store at -20°C until transfection

### Buffers

See Notion page for buffer recipes: `<YOUR_NOTION_PAGE_ID>`

## Transfection (V0 Production)

### Materials
- Bacmid DNA (from above)
- Sf9 cells at 1×10⁶ cells/mL
- ESF-921 medium
- ESF Transfection Medium
- X-tremeGene 9 transfection reagent
- 6-well plate

### Protocol

1. Air-dry bacmid pellet in TC hood (remove EtOH)
2. Dissolve in 20 µL sterile water (5-10 min)
3. Transfer 3 µL bacmid to new tube (store remainder at -20°C)
4. Plate 1 mL Sf9 (1×10⁶/mL) per well, incubate 27°C for 30 min
5. Prepare transfection mix:
   - **Mastermix:** 100 µL ESF Transfection Medium + 6 µL X-tremeGene 9 (per construct)
   - Add 100 µL ESF Transfection Medium to 3 µL bacmid, incubate 5 min
   - Add 100 µL mastermix to bacmid, incubate RT 30 min
6. Add 800 µL ESF-921 to transfection mix
7. Gently remove media from cells
8. Add 1 mL transfection mix to cells
9. Incubate 27°C for 4 hrs to overnight
10. Add 2 mL ESF-921 to prevent drying
11. Check YFP fluorescence after 2-4 days
12. Harvest V0: gently remove media, transfer to 15 mL falcon

## V1 Production

### Protocol

1. Add 0.15-3 mL V0 to 25 mL Sf9 or Sf21 at 1×10⁶ cells/mL
2. Check after 24 hrs:
   - Cells should divide once then stop
   - If no division → V0 too strong, use less next time
   - Dilute to 1×10⁶/mL if needed
3. Note day of proliferation arrest (DPA)
4. Grow additional 48-72 hrs after DPA
5. Monitor: cell viability, cell count, YFP fluorescence
6. Harvest:
   - Centrifuge 238×g for 15 min
   - Transfer supernatant (V1) to fresh 50 mL falcon
   - Store V1 at 4°C (stable ~1-1.5 years)
7. Test pellet for expression (SDS-PAGE pull-down)

## Large-Scale Expression

### Setup

- Volume: 300-600 mL per construct
- Cell lines: Hi5, Sf9, or Sf21
- Cell density: 1-2×10⁶ cells/mL at infection

### Protocol

1. Infect with V1 virus (amount determined from V1 test expression)
2. Grow 2-5 days post-infection
3. Monitor cell viability and YFP
4. Harvest when viability drops to ~80% or YFP peaks
5. Centrifuge, discard supernatant
6. Flash-freeze pellet or proceed directly to purification

### Cell Line Selection

| Cell Line | Advantages | Best For |
|-----------|------------|----------|
| Hi5 | Highest yields typically | Most proteins |
| Sf9 | Consistent, robust | Membrane proteins, difficult targets |
| Sf21 | Good yields | General use |

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| No white colonies | Plasmid issue, dead cells | Check plasmid, make fresh competent cells |
| Arc during electroporation | Salt in DNA | Re-precipitate DNA in water |
| Low transfection (no YFP) | Bad bacmid DNA, old reagents | Re-isolate bacmid, fresh X-tremeGene |
| Cells die immediately | V0 too concentrated | Use less V0 for V1 |
| Low expression | Poor virus, wrong cell line | Re-make virus, try different cell line |
| Protein degraded | Harvested too late | Harvest earlier, add protease inhibitors |

## Glycerol Stocks

Make glycerol stocks of positive DH10αEMBacY clones for future bacmid isolation:
- 500 µL culture + 500 µL 50% glycerol
- Store at -80°C

## Notion Reference

Comprehensive protocol with images: `<YOUR_NOTION_PAGE_ID>`

---

*Last updated: 2026-01-17*
