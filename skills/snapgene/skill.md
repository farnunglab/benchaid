---
name: snapgene
description: Parse SnapGene .dna files. Use when the user asks to read, convert, or extract information from SnapGene files, or needs to convert .dna to GenBank/FASTA format.
---

# SnapGene Reader

Parse SnapGene .dna files and extract sequence, features, and metadata.

## CLI Location
```
scripts/snapgene_cli.py
```

## Dependencies
```bash
pip install snapgene_reader biopython
```

## Commands

### Show Summary
```bash
python3 scripts/snapgene_cli.py 438-C.dna
```
Output: name, length, feature count, topology

### List Features
```bash
python3 scripts/snapgene_cli.py 438-C.dna --features
```
Output: table of all features (type, position, strand, name)

### Print Sequence
```bash
python3 scripts/snapgene_cli.py 438-C.dna --sequence
```
Output: raw DNA sequence

### Convert to GenBank
```bash
python3 scripts/snapgene_cli.py 438-C.dna --export-gb 438-C.gb
```

### Convert to FASTA
```bash
python3 scripts/snapgene_cli.py 438-C.dna --export-fasta 438-C.fa
```

### JSON Output
```bash
python3 scripts/snapgene_cli.py 438-C.dna --json
```
Output: full data as JSON (name, length, sequence, features with qualifiers)

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--features` | `-f` | List all features as table |
| `--sequence` | `-s` | Print DNA sequence only |
| `--export-gb FILE` | `-g` | Export to GenBank format |
| `--export-fasta FILE` | `-a` | Export to FASTA format |
| `--json` | `-j` | Output as JSON |

## Example Output

### Summary
```
SnapGene File: 438-C.dna
==================================================
Name: 438-C
Length: 6,847 bp
Features: 24
Topology: circular

Feature types:
  CDS: 4
  misc_feature: 8
  promoter: 2
  rep_origin: 1
  terminator: 2
```

### Features Table
```
Type            Start     End Strand Name
------------------------------------------------------------
promoter           1     300 +      polyhedrin promoter
CDS              500    2846 +      His6-MBP-TEV
misc_feature    2847    2864 +      LIC site
CDS             5000    5600 -      GentR
```

## Integration

Use with construct generator to load vectors:
```python
from snapgene_reader import snapgene_file_to_seqrecord

record = snapgene_file_to_seqrecord("438-C.dna")
sequence = str(record.seq)
features = record.features
```

Use with orf_verifier for clone verification:
```bash
# Convert vector to GenBank first
python3 scripts/snapgene_cli.py vector.dna --export-gb vector.gb

# Then verify clone
python3 scripts/orf_verifier_cli.py verify-clone --expected vector.gb --sequencing clone.seq
```
