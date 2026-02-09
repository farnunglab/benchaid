---
name: labbook
description: Manage lab notebook entries, registry items (plasmids, proteins, etc.), templates, widgets, and audit logs via the Labbook service. Use when creating or viewing lab notebook entries, managing the sample registry, or documenting experiments.
allowed-tools: Bash(labbookCLI:*), Bash(go:*)
---

# LabBook Skill

CLI for managing lab notebook entries, registry items, templates, widgets, and audit logs.

## Quick Start

```bash
# Setup
export $(grep LABBOOK_API_KEY .env | xargs)
cd cmd/labbookCLI

# Common queries
go run main.go registry list --kind "Protein preparation" --q "Pol II"
go run main.go registry list --kind "Plasmid"
go run main.go entries list --project "Elongation Complexes"
```

## Environment

| Variable | Description |
|----------|-------------|
| `LABBOOK_API_KEY` | API key (stored in `.env`) |
| `LABBOOK_BASE_URL` | Optional, defaults to http://localhost:4000 |

**User-specific API keys** (for proper audit attribution):
<!-- CUSTOMIZE: Add API keys for each lab member -->
- Default: `LABBOOK_API_KEY`

---

## Registry Commands

### List & Search

```bash
go run main.go registry list [--q "<search>"] [--kind "<kind>"] [--limit <n>] [--offset <n>]
go run main.go registry list --used-in-entry <entry_id>
go run main.go registry list --produced-by-entry <entry_id>
go run main.go registry list --include-entry-links
go run main.go registry get --id <id> [--show-entries]
go run main.go registry export [--out file.csv]
```

### Create & Update

```bash
# Generic
go run main.go registry create --name "<name>" --kind "<kind>" [--description "<desc>"]
go run main.go registry update --id <id> [--name] [--kind] [--description] ...

# Plasmid
go run main.go registry create --name "pLF0042" --kind Plasmid \
  --plasmid-id "pLF0042" --insert "Rpb1" --backbone "pBig1a" \
  --resistance "Amp,Gen" --sequenced yes

# Protein preparation
go run main.go registry create --name "Pol II batch 5" --kind "Protein preparation" \
  --concentration-mg-ml 2.5 --concentration-um 10 \
  --storage-buffer "20 mM HEPES pH 7.4, 300 mM NaCl" \
  --molecular-weight-da 500000 --molar-extinction-coeff 280000 \
  --prepped-by "Lucas" --prepped-on "2026-01-13" --available yes

# Expression
go run main.go registry create --name "ENL Expression 2026-01" --kind "Expression" \
  --expression-plasmid-id "pLF0009" --expression-strain "Hi5" \
  --start-date "2026-01-20" --harvest-date "2026-01-23" \
  --total-volume 600 --media "ESF921"

# Primers
go run main.go registry create --name "LF0042_F" --kind "Primers" \
  --primer-id "LF0042" --primer-sequence "ATGCGATCG..." \
  --primer-tm 62.5 --primer-gc 55

# Cryo-EM Grid
go run main.go registry create --name "ENL Grid 2026-01-25" --kind "Cryo-EM Grid" \
  --grid-id "LF-G001" --grid-type "UltrAuFoil" --grid-material "Au" \
  --grid-mesh 300 --grid-hole "R2/2" \
  --sample-ref-id 123 --sample-concentration 0.5 \
  --blot-time-s 4 --blot-force 0 --humidity 100 --temperature-c 4 \
  --ice-quality "good" --screening-notes "Nice particle distribution"
```

⚠️ **Warning:** `registry update` replaces ALL metadata. Fetch current state first, include all fields.

### Compute Proteins

Extract protein parameters from GenBank attachments on Plasmid registry items:

```bash
# Upload GenBank file first
go run main.go registry attachments upload --id <plasmid_id> --file plasmid.gb

# Compute proteins from GenBank
go run main.go registry compute-proteins --id <plasmid_id> [--overwrite] [--include-backbone]

# Update a specific protein's classification
go run main.go registry update-protein --id <plasmid_id> --index 0 \
  [--is-target true/false] [--name "Rpb1"] [--tag "His10"] [--tag-location N]
```

**Protein fields computed:**
| Field | Description |
|-------|-------------|
| `name` | Protein name (from /gene, /label, or /product) |
| `molecularWeightDa` | Molecular weight in Daltons |
| `molarExtinctionCoeff` | ε280 (M⁻¹cm⁻¹) |
| `pI` | Isoelectric point |
| `sequenceLength` | Length in amino acids |
| `tag` | Detected tag (His6, MBP, GST, etc.) |
| `tagLocation` | N or C terminal |
| `cleavageSite` | TEV, 3C, Thrombin, etc. |
| `cleavedMolecularWeightDa` | MW after cleavage |
| `cleavedMolarExtinctionCoeff` | ε280 after cleavage |
| `isTarget` | true = protein of interest |

### Attachments

```bash
go run main.go registry attachments list --id <id>
go run main.go registry attachments upload --id <id> --file /path/to/file
go run main.go registry attachments download --id <id> --attachment-id <aid> [--out file]
go run main.go registry attachments delete --id <id> --attachment-id <aid>
```

---

## Entry Commands

### List & Search

```bash
go run main.go entries list [--q "<search>"] [--project "<proj>"] [--tag "tag1,tag2"]
go run main.go entries list --from "2026-01-01" --to "2026-01-31"
go run main.go entries list --uses-registry <registry_id>
go run main.go entries list --produces-registry <registry_id>
go run main.go entries get --id <id>
```

### Create, Update & Append

```bash
# Create new entry
go run main.go entries create --title "<title>" --content-html "<html>" \
  [--project "<project>"] [--tags "tag1,tag2"] [--agent-id "benchaid"] \
  [--widgets-file /tmp/widgets.json] [--uses "122"] [--produces "123"]

# Create from file
go run main.go entries create --title "<title>" --content-file /path/to/content.html

# Update entry (replaces content)
go run main.go entries update --id <id> --title "<title>" --content-html "<html>"

# Append to existing entry (adds content without replacing)
go run main.go entries append --id <id> --append-html "<h3>Results</h3><p>...</p>"
go run main.go entries append --id <id> --append-file /tmp/results.html [--agent-id "benchaid"]

# Delete entry
go run main.go entries delete --id <id>
```

### Registry Links

```bash
go run main.go entries links --id <entry_id>
go run main.go entries link --entry-id <eid> --registry-id <rid> --type <uses|produces> [--details "<notes>"]
go run main.go entries unlink --entry-id <eid> --link-id <lid>
```

### Lock/Unlock & Versions

```bash
go run main.go entries lock --id <id>
go run main.go entries unlock --id <id>
go run main.go entries versions --id <id>
go run main.go entries restore --id <id> --version-id <vid>
```

### Export & Sharing

```bash
go run main.go entries export-html --id <id> [--out file.html]
go run main.go entries shares list --id <id>
go run main.go entries shares add --id <id> --user-email "<email>" --permission <read|write>
go run main.go entries shares delete --id <id> --share-id <sid>
```

### Attachments

```bash
go run main.go entries attachments list --id <id>
go run main.go entries attachments upload --id <id> --file /path/to/file
go run main.go entries attachments download --id <id> --attachment-id <aid> [--out file]
go run main.go entries attachments delete --id <id> --attachment-id <aid>
```

---

## Widgets

### Widget Types

```bash
go run main.go widgets types              # List all widget types
go run main.go widgets compute --widgets-file /tmp/widgets.json  # Test computation
```

| Type | Purpose | Key Inputs |
|------|---------|------------|
| `proteinParams` | Protein parameters display | name, molecularWeightDa, extinctionCoeff, pI, aminoAcids, cleaved* |
| `a280Calculator` | Concentration from A280 | a280, dilutionFactor, molecularWeightDa, molarExtinctionCoeff |
| `resultsSummary` | Prep results summary | concentrationUm, concentrationMgMl, volumeMl, aliquotSizeUl, aliquotCount |
| `registryLink` | Link to registry item | registryId |
| `formField` | Editable form field | label, inputType, value, unit |
| `calculatedField` | Auto-computed value | expression, precision |
| `yieldCalculator` | Total yield | concentrationMgMl, volumeMl |
| `dilutionCalculator` | Dilution volumes | targetConcentration, finalVolume |

### Creating Entries with Widgets

```bash
# 1. Create widgets JSON file
cat > /tmp/widgets.json << 'EOF'
[{
  "id": 0,
  "type": "proteinParams",
  "key": "enl_params",
  "measurements": {
    "name": "His6-TEV-ENL_HUMAN",
    "aminoAcids": 578,
    "molecularWeightDa": 64308,
    "extinctionCoeff": 22920,
    "pI": 8.6,
    "tag": "His6",
    "tagLocation": "N",
    "cleavageSite": "TEV",
    "cleavedName": "ENL_HUMAN",
    "cleavedAminoAcids": 562,
    "cleavedMolecularWeightDa": 62328,
    "cleavedExtinctionCoeff": 21430,
    "cleavedPI": 8.8
  },
  "source": {"registryId": 122}
}]
EOF

# 2. Create entry with widget
go run main.go entries create \
  --title "ENL Protein Parameters" \
  --content-html '<h2>ENL</h2><div data-widget="0"></div>' \
  --widgets-file /tmp/widgets.json \
  --uses 122 \
  --agent-id benchaid
```

### Widget Field Conventions

| Concept | Field Name | Notes |
|---------|------------|-------|
| Extinction coefficient | `extinctionCoeff` | Also accepts `molarExtinctionCoeff` |
| Molecular weight | `molecularWeightDa` | Always in Daltons |
| Sequence length | `aminoAcids` | Number of amino acids |
| Abs 0.1% | `abs01Percent` | Computed: ε/MW × 10 |
| Concentration µM | `concentrationUm` or `uM` | |
| Concentration mg/mL | `concentrationMgMl` or `mgMl` | |

### proteinParams Widget Example

```json
{
  "type": "proteinParams",
  "measurements": {
    "name": "His6-TEV-ProteinName",
    "aminoAcids": 500,
    "molecularWeightDa": 55000,
    "extinctionCoeff": 45000,
    "pI": 6.5,
    "tag": "His6",
    "tagLocation": "N",
    "cleavageSite": "TEV",
    "cleavedMolecularWeightDa": 53000,
    "cleavedExtinctionCoeff": 44000,
    "cleavedPI": 6.8
  }
}
```

**Computed outputs:** `abs01Percent`, `mgPerMlPerAU`, `cleavedAbs01Percent`, `cleavedMgPerMlPerAU`

### a280Calculator Widget Example

```json
{
  "type": "a280Calculator",
  "measurements": {
    "proteinName": "ENL",
    "molecularWeightDa": 64308,
    "molarExtinctionCoeff": 22920,
    "a280": 0.458,
    "dilutionFactor": 1,
    "pathLength": 1
  }
}
```

**Computed outputs:** `uM`, `mgMl`

---

## Templates

```bash
go run main.go templates list
go run main.go templates create --name "<name>" --content-html "<html>"
go run main.go templates create --name "<name>" --content-file /path/to/template.html
go run main.go templates render --id <id> --vars '{"VAR": "value"}' [--out file.html] [--out-widgets widgets.json]
go run main.go templates shares list --id <id>
go run main.go templates shares add --id <id> --user-email "<email>" --permission <read|write>
```

---

## Other Commands

```bash
# Health check
go run main.go health

# Authentication
go run main.go auth login --email "<email>" --password "<pw>"
go run main.go auth me

# Audit log
go run main.go audit list [--limit <n>]

# API keys (admin)
go run main.go api-keys create --name "<name>" --user-email "<email>" --scopes "<scope1,scope2>"

# File uploads
go run main.go uploads upload --file /path/to/file
```

---

## Registry Kinds

| Kind | Key Metadata Fields |
|------|---------------------|
| Plasmid | plasmidId, insert, backbone, resistance, sequenced, encodedProteins |
| Protein preparation | concentrationMgMl, concentrationUm, storageBuffer, molecularWeightDa, molarExtinctionCoeff, available, aliquotCount, preppedBy, preppedOn |
| Expression | expressionPlasmidId, virusId, startDate, harvestDate, media, totalVolume, expressionStrain |
| Primers | primerId, primerSequence, primerTm, primerGc, primerLength |
| Cryo-EM Grid | gridId, gridType, gridMaterial, gridMesh, gridHole, sampleConcentration, blotTimeS, blotForce, humidity, temperatureC, iceQuality, screeningNotes |

---

## Workflow Examples

### Create Entry with Protein Parameters Widget

```bash
export $(grep LABBOOK_API_KEY .env | xargs)
cd cmd/labbookCLI

# Get protein data from registry
go run main.go registry get --id 122 | jq '.targetProteins[0]'

# Create widget file with data
cat > /tmp/widget.json << 'EOF'
[{"id":0,"type":"proteinParams","key":"params","measurements":{
  "name":"His6-TEV-ENL","molecularWeightDa":64308,"extinctionCoeff":22920,
  "cleavedMolecularWeightDa":62328,"cleavedExtinctionCoeff":21430
},"source":{"registryId":122}}]
EOF

# Create entry
go run main.go entries create \
  --title "ENL Protein Parameters" \
  --content-html '<div data-widget="0"></div>' \
  --widgets-file /tmp/widget.json \
  --uses 122 --agent-id benchaid
```

### Append Results to Existing Entry

```bash
# Add SEC results to entry #34
go run main.go entries append --id 34 \
  --append-html '<h3>SEC Results</h3><p>Peak at 12.5 mL, concentration 1.2 mg/mL</p>' \
  --agent-id benchaid
```

### Plasmid → Protein Parameters Workflow

```bash
# 1. Find or create plasmid
go run main.go registry list --kind Plasmid --q "ENL"

# 2. Upload GenBank file
go run main.go registry attachments upload --id 122 --file ~/plasmids/ENL.gb

# 3. Compute proteins
go run main.go registry compute-proteins --id 122

# 4. Create entry with widget using computed data
# (protein data now available in registry metadata)
```

---

## Notes

- Content must be HTML formatted
- Tags are comma-separated
- `--merge-metadata` only merges metadata on update (otherwise replaces all)
- Use `--agent-id benchaid` for provenance tracking
- Locked entries cannot be edited until unlocked
- ε280 calculations use reduced formula (no Cys contribution)
- Widget `source.registryId` links widget to registry for data reference
- `entries append` adds content without replacing existing content
