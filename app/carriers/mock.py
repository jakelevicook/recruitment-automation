from __future__ import annotations

import asyncio
import hashlib
import random
from datetime import datetime, timedelta
from uuid import uuid4

from app.carriers.base import Carrier, CarrierError
from app.models import (
    Booking,
    Quote,
    ServiceLevel,
    ShipmentRequest,
    ShipmentStatus,
    TrackingEvent,
)


SERVICE_TRANSIT_DAYS = {
    ServiceLevel.STANDARD: 5,
    ServiceLevel.EXPEDITED: 3,
    ServiceLevel.GUARANTEED: 2,
}

SERVICE_MULTIPLIER = {
    ServiceLevel.STANDARD: 1.0,
    ServiceLevel.EXPEDITED: 1.4,
    ServiceLevel.GUARANTEED: 1.85,
}

ACCESSORIAL_FEES = {
    "liftgate_pickup": 75.0,
    "liftgate_delivery": 75.0,
    "residential_pickup": 95.0,
    "residential_delivery": 95.0,
    "inside_pickup": 110.0,
    "inside_delivery": 110.0,
}


def _seed_for(carrier_name: str, request: ShipmentRequest) -> random.Random:
    key = f"{carrier_name}|{request.origin.postal_code}|{request.destination.postal_code}|{request.total_weight:.0f}"
    digest = hashlib.sha256(key.encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


def _distance_proxy(origin_zip: str, dest_zip: str) -> float:
    try:
        o = int(origin_zip[:5])
        d = int(dest_zip[:5])
    except ValueError:
        return 1000.0
    return max(100.0, abs(o - d) * 0.85 + 250.0)


class MockCarrier(Carrier):
    def __init__(self, name: str, base_rate: float = 1.75, transit_bias: int = 0):
        self.name = name
        self.base_rate = base_rate
        self.transit_bias = transit_bias

    async def quote(self, request: ShipmentRequest) -> Quote:
        await asyncio.sleep(0.05)
        rng = _seed_for(self.name, request)

        distance = _distance_proxy(request.origin.postal_code, request.destination.postal_code)
        billable_weight = max(request.total_weight, request.total_cubic_feet * 10.0)
        class_multiplier = max(float(request.items[0].freight_class.value) / 70.0, 0.6)

        base = (distance / 100.0) * billable_weight * self.base_rate * 0.012 * class_multiplier
        base *= SERVICE_MULTIPLIER[request.service_level]

        accessorial = sum(
            fee for key, fee in ACCESSORIAL_FEES.items() if getattr(request.handling, key)
        )
        fuel_surcharge = base * (0.18 + rng.random() * 0.06)
        jitter = base * (rng.random() * 0.08 - 0.04)
        total = round(base + fuel_surcharge + accessorial + jitter, 2)

        if any(item.hazmat for item in request.items):
            total += 145.0

        transit_days = max(1, SERVICE_TRANSIT_DAYS[request.service_level] + self.transit_bias)
        pickup_date = request.pickup_date or datetime.utcnow() + timedelta(days=1)
        delivery_date = pickup_date + timedelta(days=transit_days)

        return Quote(
            carrier=self.name,
            service_level=request.service_level,
            price_usd=total,
            transit_days=transit_days,
            pickup_date=pickup_date,
            delivery_date=delivery_date,
            guaranteed=request.service_level == ServiceLevel.GUARANTEED,
            fuel_surcharge=round(fuel_surcharge, 2),
            accessorial_charges=round(accessorial, 2),
            raw={"billable_weight": round(billable_weight, 2), "distance_proxy": distance},
        )

    async def book(self, request: ShipmentRequest, quote: Quote) -> Booking:
        await asyncio.sleep(0.05)
        if any(item.hazmat for item in request.items) and self.name == "RoadRunner Express":
            raise CarrierError(f"{self.name} does not accept hazmat shipments")

        booking_id = f"bk_{uuid4().hex[:10]}"
        pro = f"{self.name[:3].upper()}-{uuid4().hex[:8].upper()}"
        return Booking(
            booking_id=booking_id,
            carrier=self.name,
            pro_number=pro,
            label_url=f"/labels/{booking_id}.pdf",
            bol_url=f"/bol/{booking_id}.pdf",
            pickup_confirmation=f"PU-{uuid4().hex[:6].upper()}",
            pickup_date=quote.pickup_date,
            estimated_delivery=quote.delivery_date,
        )

    async def track(self, booking: Booking) -> list[TrackingEvent]:
        await asyncio.sleep(0.02)
        now = datetime.utcnow()
        events: list[TrackingEvent] = [
            TrackingEvent(
                timestamp=booking.pickup_date - timedelta(hours=2),
                status=ShipmentStatus.BOOKED,
                location=None,
                description=f"Pickup scheduled with {booking.carrier} (PRO {booking.pro_number})",
            )
        ]
        if now >= booking.pickup_date:
            events.append(
                TrackingEvent(
                    timestamp=booking.pickup_date,
                    status=ShipmentStatus.IN_TRANSIT,
                    location="Origin terminal",
                    description="Freight picked up and tendered to line haul",
                )
            )
        if now >= booking.estimated_delivery:
            events.append(
                TrackingEvent(
                    timestamp=booking.estimated_delivery,
                    status=ShipmentStatus.DELIVERED,
                    location="Destination",
                    description="Freight delivered and signed for",
                )
            )
        return events
