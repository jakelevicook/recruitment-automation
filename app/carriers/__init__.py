from app.carriers.base import Carrier, CarrierError
from app.carriers.mock import MockCarrier

REGISTRY: dict[str, Carrier] = {
    "SwiftFreight": MockCarrier(name="SwiftFreight", base_rate=1.85, transit_bias=0),
    "BlueLine LTL": MockCarrier(name="BlueLine LTL", base_rate=1.60, transit_bias=1),
    "RoadRunner Express": MockCarrier(name="RoadRunner Express", base_rate=2.10, transit_bias=-1),
}


def all_carriers() -> list[Carrier]:
    return list(REGISTRY.values())


__all__ = ["Carrier", "CarrierError", "MockCarrier", "REGISTRY", "all_carriers"]
