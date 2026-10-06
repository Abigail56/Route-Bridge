from math import asin, cos, radians, sin, sqrt


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (a[0], a[1], b[0], b[1]))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(h))


def sequence_stops(stops: list[tuple[float, float]]) -> list[int]:
    """Nearest-neighbour ordering of stop indexes, starting from the first stop.

    Good enough for same-city batches; a provider-backed router can replace it behind MapProvider.route.
    """
    if not stops:
        return []
    remaining = list(range(1, len(stops)))
    order = [0]
    while remaining:
        last = stops[order[-1]]
        nxt = min(remaining, key=lambda i: haversine_km(last, stops[i]))
        remaining.remove(nxt)
        order.append(nxt)
    return order
