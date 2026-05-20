from __future__ import annotations

from abc import ABC, abstractmethod

from app.models import Booking, Quote, ShipmentRequest, TrackingEvent


class CarrierError(Exception):
    pass


class Carrier(ABC):
    name: str

    @abstractmethod
    async def quote(self, request: ShipmentRequest) -> Quote: ...

    @abstractmethod
    async def book(self, request: ShipmentRequest, quote: Quote) -> Booking: ...

    @abstractmethod
    async def track(self, booking: Booking) -> list[TrackingEvent]: ...
