from app import db, orchestrator
from app.models import (
    Address,
    FreightClass,
    FreightItem,
    Handling,
    ServiceLevel,
    ShipmentRequest,
    ShipmentStatus,
)


def make_request(hazmat=False, service=ServiceLevel.STANDARD):
    return ShipmentRequest(
        origin=Address(
            name="Alice Shipper",
            street="100 Loading Dock Rd",
            city="Newark",
            state="NJ",
            postal_code="07102",
        ),
        destination=Address(
            name="Bob Receiver",
            street="500 Warehouse Ave",
            city="Atlanta",
            state="GA",
            postal_code="30301",
        ),
        items=[
            FreightItem(
                description="Industrial parts",
                pieces=2,
                weight_lbs=400,
                length_in=48,
                width_in=40,
                height_in=36,
                freight_class=FreightClass.C70,
                hazmat=hazmat,
            )
        ],
        service_level=service,
        handling=Handling(liftgate_delivery=True),
    )


def test_automate_books_shipment():
    import asyncio

    request = make_request()
    shipment = asyncio.run(orchestrator.automate(request, selector_name="best_value"))

    assert shipment.status in {ShipmentStatus.BOOKED, ShipmentStatus.IN_TRANSIT, ShipmentStatus.DELIVERED}
    assert len(shipment.quotes) >= 1
    assert shipment.selected_quote is not None
    assert shipment.booking is not None
    assert shipment.booking.pro_number
    assert shipment.tracking, "tracking should have at least one event"


def test_cheapest_selector_picks_lowest_price():
    import asyncio

    request = make_request()
    shipment = asyncio.run(orchestrator.automate(request, selector_name="cheapest"))
    cheapest = min(shipment.quotes, key=lambda q: q.price_usd)
    assert shipment.selected_quote_id == cheapest.quote_id


def test_fastest_selector_picks_shortest_transit():
    import asyncio

    request = make_request(service=ServiceLevel.EXPEDITED)
    shipment = asyncio.run(orchestrator.automate(request, selector_name="fastest"))
    fastest = min(shipment.quotes, key=lambda q: (q.transit_days, q.price_usd))
    assert shipment.selected_quote_id == fastest.quote_id


def test_hazmat_fails_over_when_carrier_refuses():
    import asyncio
    from app.carriers import REGISTRY

    request = make_request(hazmat=True)
    # Force RoadRunner to be cheapest so failover is exercised:
    rr = REGISTRY["RoadRunner Express"]
    original = rr.base_rate
    rr.base_rate = 0.5
    try:
        shipment = asyncio.run(orchestrator.automate(request, selector_name="cheapest"))
    finally:
        rr.base_rate = original

    assert shipment.status == ShipmentStatus.BOOKED or shipment.status == ShipmentStatus.IN_TRANSIT or shipment.status == ShipmentStatus.DELIVERED
    assert shipment.booking is not None
    assert shipment.booking.carrier != "RoadRunner Express"


def test_persistence_roundtrip():
    import asyncio

    request = make_request()
    shipment = asyncio.run(orchestrator.automate(request))
    loaded = db.get(shipment.id)
    assert loaded is not None
    assert loaded.id == shipment.id
    assert loaded.status == shipment.status


def test_quote_pricing_deterministic_per_request():
    import asyncio
    from app.carriers import MockCarrier

    carrier = MockCarrier("DeterminismCheck", base_rate=1.75)
    request = make_request()
    q1 = asyncio.run(carrier.quote(request))
    q2 = asyncio.run(carrier.quote(request))
    assert q1.price_usd == q2.price_usd
