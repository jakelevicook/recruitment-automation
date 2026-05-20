from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class FreightClass(str, Enum):
    C50 = "50"
    C55 = "55"
    C60 = "60"
    C65 = "65"
    C70 = "70"
    C77_5 = "77.5"
    C85 = "85"
    C92_5 = "92.5"
    C100 = "100"
    C110 = "110"
    C125 = "125"
    C150 = "150"
    C175 = "175"
    C200 = "200"
    C250 = "250"
    C300 = "300"
    C400 = "400"
    C500 = "500"


class ServiceLevel(str, Enum):
    STANDARD = "standard"
    EXPEDITED = "expedited"
    GUARANTEED = "guaranteed"


class ShipmentStatus(str, Enum):
    DRAFT = "draft"
    QUOTING = "quoting"
    QUOTED = "quoted"
    BOOKING = "booking"
    BOOKED = "booked"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    FAILED = "failed"


class Address(BaseModel):
    name: str
    company: Optional[str] = None
    street: str
    city: str
    state: str = Field(min_length=2, max_length=2)
    postal_code: str
    country: str = "US"
    phone: Optional[str] = None

    @field_validator("state")
    @classmethod
    def upper_state(cls, v: str) -> str:
        return v.upper()


class Handling(BaseModel):
    liftgate_pickup: bool = False
    liftgate_delivery: bool = False
    residential_pickup: bool = False
    residential_delivery: bool = False
    inside_pickup: bool = False
    inside_delivery: bool = False


class FreightItem(BaseModel):
    description: str
    pieces: int = Field(gt=0)
    weight_lbs: float = Field(gt=0)
    length_in: float = Field(gt=0)
    width_in: float = Field(gt=0)
    height_in: float = Field(gt=0)
    freight_class: FreightClass = FreightClass.C70
    nmfc: Optional[str] = None
    stackable: bool = True
    hazmat: bool = False

    @property
    def cubic_feet(self) -> float:
        return (self.length_in * self.width_in * self.height_in * self.pieces) / 1728.0

    @property
    def total_weight(self) -> float:
        return self.weight_lbs * self.pieces


class ShipmentRequest(BaseModel):
    origin: Address
    destination: Address
    items: list[FreightItem] = Field(min_length=1)
    service_level: ServiceLevel = ServiceLevel.STANDARD
    handling: Handling = Field(default_factory=Handling)
    reference: Optional[str] = None
    pickup_date: Optional[datetime] = None

    @property
    def total_weight(self) -> float:
        return sum(i.total_weight for i in self.items)

    @property
    def total_cubic_feet(self) -> float:
        return sum(i.cubic_feet for i in self.items)


class Quote(BaseModel):
    quote_id: str = Field(default_factory=lambda: f"q_{uuid4().hex[:12]}")
    carrier: str
    service_level: ServiceLevel
    price_usd: float
    transit_days: int
    pickup_date: datetime
    delivery_date: datetime
    guaranteed: bool = False
    fuel_surcharge: float = 0.0
    accessorial_charges: float = 0.0
    raw: dict = Field(default_factory=dict)


class Booking(BaseModel):
    booking_id: str
    carrier: str
    pro_number: str
    label_url: Optional[str] = None
    bol_url: Optional[str] = None
    pickup_confirmation: str
    pickup_date: datetime
    estimated_delivery: datetime


class TrackingEvent(BaseModel):
    timestamp: datetime
    status: ShipmentStatus
    location: Optional[str] = None
    description: str


class Shipment(BaseModel):
    id: str = Field(default_factory=lambda: f"shp_{uuid4().hex[:12]}")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    status: ShipmentStatus = ShipmentStatus.DRAFT
    request: ShipmentRequest
    quotes: list[Quote] = Field(default_factory=list)
    selected_quote_id: Optional[str] = None
    booking: Optional[Booking] = None
    tracking: list[TrackingEvent] = Field(default_factory=list)
    error: Optional[str] = None

    @property
    def selected_quote(self) -> Optional[Quote]:
        if not self.selected_quote_id:
            return None
        return next((q for q in self.quotes if q.quote_id == self.selected_quote_id), None)
