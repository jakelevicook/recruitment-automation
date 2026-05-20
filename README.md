# FreightAuto — Fully Automated Freight Shipment

A self-driving freight shipment platform: submit a shipment once, and the
system handles **quoting → carrier selection → booking → BOL/label →
tracking** without any human intervention.

No phone calls. No office. No back-and-forth with brokers.

## What it does

- Solicits **parallel quotes** from every configured carrier
- **Auto-selects** the winning quote (`cheapest` / `fastest` / `best_value`)
- **Books** the shipment with the selected carrier (with automatic
  failover to the next-best option if the primary refuses, e.g. hazmat)
- Generates BOL & shipping label URLs
- Pulls **tracking events** and stores everything in SQLite
- Exposes a **web dashboard**, a **REST API**, and a **CLI** — pick your
  poison

## Quickstart

```bash
pip install -r requirements.txt

# Web dashboard at http://localhost:8000
python cli.py serve

# Or one-shot from the CLI:
python cli.py ship \
  --origin   "Alice,100 Loading Dock Rd,Newark,NJ,07102" \
  --destination "Bob,500 Warehouse Ave,Atlanta,GA,30301" \
  --weight 400 --pieces 2 --service expedited --selector best_value
```

## REST API

```
POST /api/shipments              # automate a shipment end-to-end
GET  /api/shipments              # list
GET  /api/shipments/{id}
POST /api/shipments/{id}/track   # refresh tracking
GET  /healthz
```

Body for `POST /api/shipments` is a `ShipmentRequest` (see `app/models.py`).

## Architecture

```
app/
  models.py            # Pydantic models: Address, FreightItem, Shipment, ...
  carriers/
    base.py            # Carrier interface (quote / book / track)
    mock.py            # Deterministic mock carrier with realistic LTL pricing
    __init__.py        # Registry of carriers
  orchestrator.py      # The fully-automated pipeline + selectors
  db.py                # SQLite persistence
  api.py               # FastAPI app + Jinja dashboard
  templates/, static/  # Dashboard UI
cli.py                 # Typer CLI: ship / track / list / batch / serve
tests/                 # pytest suite
```

The `Carrier` interface in `app/carriers/base.py` is the only thing you
need to implement to drop in a real carrier (FedEx Freight, XPO, Project44,
etc.). The orchestrator and the rest of the system don't know or care
that the bundled carriers are mocks.

## Tests

```bash
pytest
```
