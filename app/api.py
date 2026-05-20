from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import db, orchestrator
from app.carriers import all_carriers
from app.models import (
    Address,
    FreightClass,
    FreightItem,
    Handling,
    ServiceLevel,
    ShipmentRequest,
)

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Automated Freight Shipment Platform", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    shipments = db.list_all()
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "shipments": shipments,
            "carriers": [c.name for c in all_carriers()],
            "service_levels": [s.value for s in ServiceLevel],
            "freight_classes": [f.value for f in FreightClass],
        },
    )


@app.get("/shipments/{shipment_id}", response_class=HTMLResponse)
async def shipment_detail(request: Request, shipment_id: str):
    shipment = db.get(shipment_id)
    if not shipment:
        raise HTTPException(404, "Shipment not found")
    return templates.TemplateResponse(
        "shipment.html", {"request": request, "shipment": shipment}
    )


@app.post("/shipments")
async def create_shipment_form(
    request: Request,
    origin_name: str = Form(...),
    origin_company: str = Form(""),
    origin_street: str = Form(...),
    origin_city: str = Form(...),
    origin_state: str = Form(...),
    origin_zip: str = Form(...),
    dest_name: str = Form(...),
    dest_company: str = Form(""),
    dest_street: str = Form(...),
    dest_city: str = Form(...),
    dest_state: str = Form(...),
    dest_zip: str = Form(...),
    item_description: str = Form(...),
    pieces: int = Form(...),
    weight_lbs: float = Form(...),
    length_in: float = Form(...),
    width_in: float = Form(...),
    height_in: float = Form(...),
    freight_class: str = Form("70"),
    service_level: str = Form("standard"),
    liftgate_pickup: Optional[str] = Form(None),
    liftgate_delivery: Optional[str] = Form(None),
    residential_delivery: Optional[str] = Form(None),
    hazmat: Optional[str] = Form(None),
    selector: str = Form("best_value"),
    reference: str = Form(""),
):
    req = ShipmentRequest(
        origin=Address(
            name=origin_name,
            company=origin_company or None,
            street=origin_street,
            city=origin_city,
            state=origin_state,
            postal_code=origin_zip,
        ),
        destination=Address(
            name=dest_name,
            company=dest_company or None,
            street=dest_street,
            city=dest_city,
            state=dest_state,
            postal_code=dest_zip,
        ),
        items=[
            FreightItem(
                description=item_description,
                pieces=pieces,
                weight_lbs=weight_lbs,
                length_in=length_in,
                width_in=width_in,
                height_in=height_in,
                freight_class=FreightClass(freight_class),
                hazmat=bool(hazmat),
            )
        ],
        service_level=ServiceLevel(service_level),
        handling=Handling(
            liftgate_pickup=bool(liftgate_pickup),
            liftgate_delivery=bool(liftgate_delivery),
            residential_delivery=bool(residential_delivery),
        ),
        reference=reference or None,
    )
    shipment = await orchestrator.automate(req, selector_name=selector)
    return RedirectResponse(url=f"/shipments/{shipment.id}", status_code=303)


@app.post("/api/shipments")
async def create_shipment_api(request: ShipmentRequest, selector: str = "best_value"):
    shipment = await orchestrator.automate(request, selector_name=selector)
    return JSONResponse(shipment.model_dump(mode="json"))


@app.get("/api/shipments")
async def list_shipments_api():
    return [s.model_dump(mode="json") for s in db.list_all()]


@app.get("/api/shipments/{shipment_id}")
async def get_shipment_api(shipment_id: str):
    shipment = db.get(shipment_id)
    if not shipment:
        raise HTTPException(404, "Shipment not found")
    return shipment.model_dump(mode="json")


@app.post("/api/shipments/{shipment_id}/track")
async def refresh_tracking_api(shipment_id: str):
    shipment = await orchestrator.refresh_tracking(shipment_id)
    if not shipment:
        raise HTTPException(404, "Shipment not found")
    return shipment.model_dump(mode="json")


@app.get("/healthz")
async def healthz():
    return {"ok": True, "carriers": [c.name for c in all_carriers()]}
