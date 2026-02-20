---
name: twist-order
description: Order DNA synthesis from Twist Bioscience. Use when the user asks to order clonal genes, gene blocks, or gene fragments from Twist, or to submit codon-optimized sequences for synthesis.
---

# Twist Bioscience DNA Ordering

Order clonal genes, gene blocks, and gene fragments via Twist Bioscience API.

## CLI Location
```
twist_order
```

## Environment
Set in `.env`:
- `TWIST_API_TOKEN` - Twist API token
- `TWIST_USER_EMAIL` - Twist account email

## Commands

### Order Clonal Gene (into vector)
```bash
twist_order gene \
  --sequence <DNA> \
  --name <NAME> \
  --vector-id <VECTOR_MES_UID> \
  --insertion-point-id <INSERTION_POINT_MES_UID> \
  --recipient-address-id <ADDRESS_ID> \
  --first-name <FIRST> \
  --last-name <LAST> \
  --phone <PHONE> \
  --payment-method-id <PAYMENT_ID>
```

### Order Gene Block / Fragment (linear DNA)
```bash
twist_order gene-block \
  --sequence <DNA> \
  --name <NAME> \
  --recipient-address-id <ADDRESS_ID> \
  --first-name <FIRST> \
  --last-name <LAST> \
  --phone <PHONE> \
  --payment-method-id <PAYMENT_ID>
```

### List Available Vectors
```bash
twist_order vectors list
```

## Key Options

| Option | Description |
|--------|-------------|
| `--sequence` | DNA sequence (A/C/T/G/N only) |
| `--sequence-file` | Path to file with DNA sequence (FASTA OK) |
| `--name` | Construct name |
| `--vector-id` | Vector MES UID (clonal genes only) |
| `--insertion-point-id` | Insertion point MES UID (clonal genes only) |
| `--adapters-on` | Enable adapters for gene fragments |
| `--glycerol-stock` | Add glycerol stock (clonal genes) |
| `--quote-only` | Create quote only, don't place order |
| `--no-po` | Order without PO (if allowed) |

## Delivery Options

| Option | Default | Description |
|--------|---------|-------------|
| `--dna-scale` | `GENE_PREP_MICRO` | DNA scale product code |
| `--delivery-format` | `SER_PKG_TUBE` | Tube or plate format |
| `--buffer-code` | (none) | Optional buffer product code |
| `--normalization` | 0 | Normalization value (0.5-2.0) |

## Typical Workflow

1. **Codon optimize** (IDT):
   ```bash
   python3 scripts/codon_optimize_cli.py --accession NP_003161 --organism insect --fasta > spt6_opt.fa
   ```

2. **Get quote** (Twist):
   ```bash
   twist_order gene \
     --sequence-file spt6_opt.fa \
     --name SUPT6H_insect \
     --vector-id <from vectors list> \
     --insertion-point-id <from vectors list> \
     --recipient-address-id <your address> \
     --first-name <FIRST> --last-name <LAST> \
     --phone <phone> \
     --quote-only
   ```

3. **Place order** (remove `--quote-only`, add `--payment-method-id`)

## Notes

- Clonal genes require vector and insertion point IDs (get from `vectors list`)
- Gene blocks/fragments are linear DNA, no vector required
- API waits for scoring and quote generation (up to 10 min each)
- Use `--quote-only` to review pricing before ordering
