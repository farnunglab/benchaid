---
name: quartzy
description: Query and manage Quartzy lab inventory, order requests, and webhooks. Use when the user asks about lab supplies, reagent inventory, placing orders, checking order status, or creating new order requests in Quartzy.
allowed-tools: Bash(quartzy:*), Bash(quartzy:*)
---

# Quartzy Skill

Query and manage the lab's Quartzy inventory, order requests, and webhooks.

## Configuration

The CLI reads from `.env` in the working directory:
- `QUARTZY_KEY` - API access token (generate at https://app.quartzy.com/profile/access-tokens)
- `QUARTZY_LAB_ID` - Default lab ID (used when --lab-id not specified)
- `QUARTZY_ORGANIZATION_ID` - Default organization ID (used when --organization-id not specified)
- `QUARTZY_BASE_URL` - Optional, defaults to https://api.quartzy.com

## Tool Location

`quartzy`

## API Limitations

**Important:** The Quartzy API has significant limitations:
- **Listing order requests only returns historical items** (RECEIVED, CANCELLED) — pending/new requests are not returned
- **Status filters are ignored** by the list endpoint
- **Creating, getting by ID, and updating status all work correctly**
- To see pending requests, use the web UI: https://app.quartzy.com/groups/239714/requests?status[]=PENDING

## Commands

### Health Check

```bash
quartzy health
```

### User Info

```bash
quartzy user
```

### Labs

```bash
# List labs in organization (uses QUARTZY_ORGANIZATION_ID from .env)
quartzy labs list [--page <N>]

# Get specific lab details
quartzy labs get --id <UUID>
```

### Inventory

```bash
# List inventory items (uses QUARTZY_LAB_ID from .env)
quartzy inventory list [--page <N>]

# Get specific inventory item
quartzy inventory get --id <UUID>

# Update inventory quantity
quartzy inventory update --id <UUID> --quantity <VALUE>
```

### Order Requests

```bash
# List order requests (NOTE: only returns historical/completed items)
quartzy order-requests list [--page <N>]

# Get specific order request by ID (works for any status including pending)
quartzy order-requests get --id <UUID>

# Create new order request
quartzy order-requests create \
  --type-id <UUID> \
  --name <NAME> \
  --vendor-name <NAME> \
  --catalog-number <NUM> \
  --price-amount <INT> \
  --price-currency <CODE> \
  --quantity <INT> \
  [--vendor-product-id <UUID>] \
  [--required-before <YYYY-MM-DD>] \
  [--notes <TEXT>]

# Update order request status
quartzy order-requests update --id <UUID> --status <STATUS>
# Status: CREATED | CANCELLED | APPROVED | ORDERED | BACKORDERED | RECEIVED
```

### Inventory Types

Use these type IDs when creating order requests:

| Type | ID |
|------|-----|
| Antibody | `6860e5fb-40f0-4924-9061-1690f2f65def` |
| Cell Line | `1564c547-a877-4a6f-8614-910d7b01b8b7` |
| Chemical | `cd4aa642-7f42-4f45-ac2a-2a4b04a147ae` |
| Enzyme - Restriction | `f0f74a0a-81fa-45e3-a59e-36ebce7dbecd` |
| General Supply | `8f404ec9-141e-48d4-9ea5-eecd65d91f38` |

```bash
# List all inventory types
quartzy types list [--name <NAME>] [--page <N>]
```

### Webhooks

```bash
# List webhooks (uses QUARTZY_ORGANIZATION_ID from .env)
quartzy webhooks list [--page <N>]

# Get specific webhook
quartzy webhooks get --id <UUID>

# Create webhook
quartzy webhooks create \
  --url <URL> \
  [--name <NAME>] \
  [--event-types <CSV>] \
  [--is-enabled <true|false>]

# Update webhook
quartzy webhooks update --id <UUID> --is-enabled <true|false>
```

## Examples

User: "What's in our Quartzy inventory?"
```bash
quartzy inventory list
```

User: "Create an order request for 2 boxes of pipette tips from VWR"
```bash
quartzy order-requests create \
  --type-id 8f404ec9-141e-48d4-9ea5-eecd65d91f38 \
  --name "Pipette Tips 200uL" \
  --vendor-name "VWR" \
  --catalog-number "89079-478" \
  --price-amount 4500 \
  --price-currency USD \
  --quantity 2
```

User: "Get details for order request abc-123"
```bash
quartzy order-requests get --id abc-123
```

User: "Mark order abc-123 as received"
```bash
quartzy order-requests update --id abc-123 --status RECEIVED
```

User: "Cancel order abc-123"
```bash
quartzy order-requests update --id abc-123 --status CANCELLED
```

User: "What inventory types do we have?"
```bash
quartzy types list
```

User: "Update the quantity of inventory item xyz to 5"
```bash
quartzy inventory update --id xyz --quantity 5
```

## Notes

- All commands output JSON for easy parsing
- Lab and organization IDs default from .env; override with --lab-id or --organization-id
- Use `--token <TOKEN>` flag to override the API token
- Pagination: use `--page N` to navigate through results
- Price amount is in cents (e.g., 4500 = $45.00)
- The web UI shows "PENDING" status but the API uses "CREATED" for new requests
