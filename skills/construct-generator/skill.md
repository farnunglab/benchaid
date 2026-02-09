# Construct Generator

Generate expected plasmid maps by combining vector backbones with insert sequences. Essential for clone verification workflows.

## CLI Location

```bash
./construct_generator [flags]
```

## What It Does

The construct generator creates in-silico plasmid maps representing the expected product of a cloning reaction. It:

1. Loads a vector backbone (from built-in library or local files)
2. Fetches an insert sequence (from NCBI or local file)
3. Simulates the cloning reaction based on method (LIC, Gibson, SLIC, restriction)
4. Outputs a GenBank file with proper annotations

## Usage

### List Available Vectors

```bash
./construct_generator -list-vectors
```

Shows all vectors from:
- Built-in defaults (438 series, common expression vectors)
- `~/.benchaid/vectors.yaml` (user-defined)
- `vectors/*.yaml` (project-specific)

### Generate a Construct

**From NCBI accession:**
```bash
./construct_generator \
  -vector 438-A \
  -insert-accession NM_007192 \
  -output my_construct.gb
```

**From local file:**
```bash
./construct_generator \
  -vector 438-A \
  -insert-file insert.fasta \
  -gene-name MyProtein \
  -output my_construct.gb
```

### Cloning Methods

| Method | Flag | Description |
|--------|------|-------------|
| LIC | `-method lic` | Ligation Independent Cloning (default) |
| Gibson | `-method gibson` | Gibson Assembly |
| SLIC | `-method slic` | Sequence and Ligation Independent Cloning |
| Restriction | `-method restriction` | Traditional restriction enzyme cloning |

### Key Flags

| Flag | Description |
|------|-------------|
| `-vector` | Vector name (from library) or path to .gb/.yaml file |
| `-insert-accession` | NCBI accession (NM_, NP_, XP_ prefixes) |
| `-insert-file` | Local FASTA/GenBank file for insert |
| `-gene-name` | Gene name for annotations (auto-detected from accession) |
| `-output` | Output GenBank file path |
| `-method` | Cloning method: lic, gibson, slic, restriction |
| `-json` | Also output JSON metadata |
| `-validate` | Run validation checks (frame, stop codons) |
| `-list-vectors` | List all available vectors |

## Vector Library

### Built-in 438 Series

The 438 series vectors are bacterial expression vectors with various fusion tags:

| Vector | Tag | Notes |
|--------|-----|-------|
| 438-A | His6 | N-terminal His tag |
| 438-B | His6-MBP | Maltose binding protein fusion |
| 438-C | His6-GST | Glutathione S-transferase fusion |
| 438-D | His6-Trx | Thioredoxin fusion |
| 438-E | His6-NusA | NusA fusion for solubility |
| 438-F | His6-SUMO | SUMO fusion with protease site |
| 438-G | His6-GB1 | GB1 domain fusion |
| 438-H | His6-Halo | HaloTag fusion |

### Local Vectors

GenBank files in `./vectors/` are automatically available:
- `vectors/438-A.gb` through `vectors/438-H.gb`

### Adding Custom Vectors

Create a YAML file in `vectors/` or `~/.benchaid/vectors.yaml`:

```yaml
vectors:
  my-vector:
    file: path/to/vector.gb
    insert_site: 1234  # Position for insert
    method: lic        # Default cloning method
    description: "My custom expression vector"
```

## Validation

When `-validate` is enabled, the tool checks:

1. **Frame check**: Insert is in-frame with vector ORF
2. **Internal stops**: No premature stop codons in the fusion
3. **Insert length**: Reasonable size for expression

## Output Format

The output GenBank file includes:

- Full plasmid sequence with insert
- Annotated features:
  - Vector backbone elements
  - Insert CDS with gene name
  - Fusion tags
  - Promoters, terminators, origins
- Metadata in COMMENT section

## Example Workflows

### Standard Cloning Project

```bash
# 1. Design primers for the insert
./primer_cli.py --accession NM_007192 --index 1

# 2. Generate expected construct
./construct_generator \
  -vector 438-B \
  -insert-accession NM_007192 \
  -output expected_construct.gb

# 3. After cloning and sequencing, verify with orf_verifier
python3 scripts/orf_verifier_cli.py \
  --plasmid expected_construct.gb \
  --protein MKHHHHHHMS...
```

### Using Local Insert File

```bash
# Generate construct from synthesized gene
./construct_generator \
  -vector 438-A \
  -insert-file synthesized_gene.fasta \
  -gene-name DSIF \
  -method lic \
  -output dsif_construct.gb
```

### Batch Processing

```bash
# Generate constructs for multiple accessions
for acc in NM_007192 NM_001234 NM_005678; do
  ./construct_generator \
    -vector 438-B \
    -insert-accession $acc \
    -output constructs/${acc}.gb
done
```

## Integration with Other Tools

| Tool | Integration |
|------|-------------|
| primer_cli.py | Design primers for the same accession |
| orf_verifier_cli.py | Verify clones against expected construct |
| snapgene_cli.py | Convert SnapGene vectors to GenBank format |
| notion_cli.py | Download vectors from Notion database |

## Troubleshooting

**"Vector not found"**
- Run `-list-vectors` to see available vectors
- Check that vector files exist in `vectors/` directory
- Ensure GenBank files have proper LOCUS line

**"Could not fetch accession"**
- Verify the accession exists at NCBI
- Check internet connectivity
- Use `-insert-file` with a local file instead

**"Frame validation failed"**
- The insert may not be in-frame with vector
- Check primer design includes correct reading frame
- Use `-validate=false` to skip validation if intentional
