from fastapi.testclient import TestClient

from app.api import app

client = TestClient(app)


SAMPLE = {
    "origin": {
        "name": "Alice Shipper",
        "street": "100 Loading Dock Rd",
        "city": "Newark",
        "state": "NJ",
        "postal_code": "07102",
    },
    "destination": {
        "name": "Bob Receiver",
        "street": "500 Warehouse Ave",
        "city": "Atlanta",
        "state": "GA",
        "postal_code": "30301",
    },
    "items": [
        {
            "description": "Industrial parts",
            "pieces": 2,
            "weight_lbs": 400,
            "length_in": 48,
            "width_in": 40,
            "height_in": 36,
            "freight_class": "70",
        }
    ],
    "service_level": "standard",
}


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_create_and_fetch_shipment_via_api():
    r = client.post("/api/shipments", json=SAMPLE)
    assert r.status_code == 200
    shipment = r.json()
    assert shipment["status"] in {"booked", "in_transit", "delivered"}
    assert shipment["booking"] is not None
    assert shipment["selected_quote_id"]

    r2 = client.get(f"/api/shipments/{shipment['id']}")
    assert r2.status_code == 200
    assert r2.json()["id"] == shipment["id"]


def test_dashboard_renders():
    r = client.get("/")
    assert r.status_code == 200
    assert "Book a shipment" in r.text


def test_refresh_tracking():
    created = client.post("/api/shipments", json=SAMPLE).json()
    r = client.post(f"/api/shipments/{created['id']}/track")
    assert r.status_code == 200
    assert r.json()["tracking"]
