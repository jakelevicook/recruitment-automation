from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer

from app import db, orchestrator
from app.models import (
    Address,
    FreightClass,
    FreightItem,
    Handling,
    ServiceLevel,
    ShipmentRequest,
)

cli = typer.Typer(help="Fully-automated freight shipment CLI.")


def _build_request(
    origin: str,
    destination: str,
    weight: float,
    pieces: int,
    description: str,
    freight_class: str,
    service: str,
    liftgate_delivery: bool,
    residential_delivery: bool,
    hazmat: bool,
) -> ShipmentRequest:
    def parse(addr: str, label: str) -> Address:
        parts = [p.strip() for p in addr.split(",")]
        if len(parts) < 4:
            raise typer.BadParameter(
                f"--{label} must be 'name,street,city,state,zip' (got {addr!r})"
            )
        name, street, city, state, postal = parts[0], parts[1], parts[2], parts[3], parts[4]
        return Address(
            name=name, street=street, city=city, state=state, postal_code=postal
        )

    return ShipmentRequest(
        origin=parse(origin, "origin"),
        destination=parse(destination, "destination"),
        items=[
            FreightItem(
                description=description,
                pieces=pieces,
                weight_lbs=weight,
                length_in=48,
                width_in=40,
                height_in=36,
                freight_class=FreightClass(freight_class),
                hazmat=hazmat,
            )
        ],
        service_level=ServiceLevel(service),
        handling=Handling(
            liftgate_delivery=liftgate_delivery,
            residential_delivery=residential_delivery,
        ),
    )


@cli.command()
def ship(
    origin: str = typer.Option(..., help="name,street,city,state,zip"),
    destination: str = typer.Option(..., help="name,street,city,state,zip"),
    weight: float = typer.Option(..., help="lbs per piece"),
    pieces: int = typer.Option(1),
    description: str = typer.Option("Palletized goods"),
    freight_class: str = typer.Option("70"),
    service: str = typer.Option("standard"),
    selector: str = typer.Option("best_value", help="cheapest | fastest | best_value"),
    liftgate_delivery: bool = typer.Option(False),
    residential_delivery: bool = typer.Option(False),
    hazmat: bool = typer.Option(False),
    json_out: bool = typer.Option(False, "--json"),
):
    """Run the full automated pipeline: quote -> book -> label -> track."""
    request = _build_request(
        origin, destination, weight, pieces, description, freight_class,
        service, liftgate_delivery, residential_delivery, hazmat,
    )
    shipment = asyncio.run(orchestrator.automate(request, selector_name=selector))

    if json_out:
        typer.echo(shipment.model_dump_json(indent=2))
        return

    typer.echo(f"\nShipment {shipment.id}  [{shipment.status.value}]")
    if shipment.error:
        typer.echo(f"  error: {shipment.error}")
        raise typer.Exit(1)

    typer.echo("\nQuotes:")
    for q in shipment.quotes:
        marker = "  *" if q.quote_id == shipment.selected_quote_id else "   "
        typer.echo(
            f"{marker} {q.carrier:<22} {q.service_level.value:<11} "
            f"{q.transit_days}d  ${q.price_usd:>8.2f}"
        )
    if shipment.booking:
        b = shipment.booking
        typer.echo(
            f"\nBooked with {b.carrier}: PRO {b.pro_number}, pickup {b.pickup_date:%Y-%m-%d}, ETA {b.estimated_delivery:%Y-%m-%d}"
        )
        typer.echo(f"  label: {b.label_url}\n  bol:   {b.bol_url}")


@cli.command()
def track(shipment_id: str):
    """Refresh tracking for a previously created shipment."""
    shipment = asyncio.run(orchestrator.refresh_tracking(shipment_id))
    if not shipment:
        typer.echo(f"No shipment {shipment_id}", err=True)
        raise typer.Exit(1)
    for e in shipment.tracking:
        typer.echo(f"  {e.timestamp:%Y-%m-%d %H:%M}  {e.status.value:<12} {e.description}")


@cli.command(name="list")
def list_cmd():
    """List recent shipments."""
    for s in db.list_all():
        carrier = s.selected_quote.carrier if s.selected_quote else "—"
        price = f"${s.selected_quote.price_usd:.2f}" if s.selected_quote else "—"
        typer.echo(f"{s.id}  {s.status.value:<12} {carrier:<22} {price}")


@cli.command()
def batch(file: Path = typer.Argument(..., help="JSON file with a list of ShipmentRequest")):
    """Automate many shipments from a JSON file. No human touch required."""
    payload = json.loads(file.read_text())
    requests = [ShipmentRequest.model_validate(p) for p in payload]

    async def run_all():
        results = []
        for r in requests:
            results.append(await orchestrator.automate(r))
        return results

    results = asyncio.run(run_all())
    for r in results:
        typer.echo(f"{r.id}  {r.status.value}")


@cli.command()
def serve(host: str = "0.0.0.0", port: int = 8000):
    """Run the FastAPI dashboard."""
    import uvicorn
    uvicorn.run("app.api:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    cli()
