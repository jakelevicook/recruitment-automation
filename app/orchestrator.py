from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Callable, Optional

from app import db
from app.carriers import Carrier, CarrierError, all_carriers
from app.models import Quote, Shipment, ShipmentRequest, ShipmentStatus, TrackingEvent

log = logging.getLogger("freight.orchestrator")


QuoteSelector = Callable[[list[Quote]], Quote]


def cheapest(quotes: list[Quote]) -> Quote:
    return min(quotes, key=lambda q: q.price_usd)


def fastest(quotes: list[Quote]) -> Quote:
    return min(quotes, key=lambda q: (q.transit_days, q.price_usd))


def best_value(quotes: list[Quote]) -> Quote:
    return min(quotes, key=lambda q: q.price_usd + q.transit_days * 25.0)


SELECTORS: dict[str, QuoteSelector] = {
    "cheapest": cheapest,
    "fastest": fastest,
    "best_value": best_value,
}


async def _gather_quotes(carriers: list[Carrier], request: ShipmentRequest) -> list[Quote]:
    tasks = [c.quote(request) for c in carriers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    quotes: list[Quote] = []
    for carrier, result in zip(carriers, results):
        if isinstance(result, Exception):
            log.warning("Quote failed for %s: %s", carrier.name, result)
            continue
        quotes.append(result)
    return quotes


def _carrier_by_name(name: str) -> Carrier:
    for c in all_carriers():
        if c.name == name:
            return c
    raise CarrierError(f"Unknown carrier: {name}")


async def automate(
    request: ShipmentRequest,
    selector_name: str = "best_value",
    carriers: Optional[list[Carrier]] = None,
) -> Shipment:
    """Run the full pipeline: quote -> select -> book -> initial track. Fully unattended."""
    selector = SELECTORS.get(selector_name, best_value)
    carriers = carriers or all_carriers()
    shipment = Shipment(request=request, status=ShipmentStatus.QUOTING)
    db.save(shipment)

    try:
        quotes = await _gather_quotes(carriers, request)
        if not quotes:
            shipment.status = ShipmentStatus.FAILED
            shipment.error = "No carriers returned a quote"
            shipment.updated_at = datetime.utcnow()
            db.save(shipment)
            return shipment

        shipment.quotes = quotes
        shipment.status = ShipmentStatus.QUOTED
        shipment.updated_at = datetime.utcnow()
        db.save(shipment)

        chosen = selector(quotes)
        shipment.selected_quote_id = chosen.quote_id
        shipment.status = ShipmentStatus.BOOKING
        shipment.updated_at = datetime.utcnow()
        db.save(shipment)

        carrier = _carrier_by_name(chosen.carrier)
        try:
            booking = await carrier.book(request, chosen)
        except CarrierError as e:
            remaining = sorted(
                (q for q in quotes if q.quote_id != chosen.quote_id),
                key=lambda q: q.price_usd,
            )
            if not remaining:
                raise
            log.warning("Primary carrier %s failed (%s); failing over", chosen.carrier, e)
            fallback = remaining[0]
            shipment.selected_quote_id = fallback.quote_id
            db.save(shipment)
            booking = await _carrier_by_name(fallback.carrier).book(request, fallback)

        shipment.booking = booking
        shipment.status = ShipmentStatus.BOOKED
        shipment.updated_at = datetime.utcnow()

        events = await _carrier_by_name(booking.carrier).track(booking)
        shipment.tracking = events
        if events:
            shipment.status = events[-1].status
        shipment.updated_at = datetime.utcnow()
        db.save(shipment)
        return shipment

    except Exception as e:
        log.exception("Automation failed for %s", shipment.id)
        shipment.status = ShipmentStatus.FAILED
        shipment.error = str(e)
        shipment.updated_at = datetime.utcnow()
        db.save(shipment)
        return shipment


async def refresh_tracking(shipment_id: str) -> Optional[Shipment]:
    shipment = db.get(shipment_id)
    if not shipment or not shipment.booking:
        return shipment
    carrier = _carrier_by_name(shipment.booking.carrier)
    events: list[TrackingEvent] = await carrier.track(shipment.booking)
    shipment.tracking = events
    if events:
        shipment.status = events[-1].status
    shipment.updated_at = datetime.utcnow()
    db.save(shipment)
    return shipment
