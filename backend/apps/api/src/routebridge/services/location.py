"""Location confidence scoring and Open Location Code (plus code) handling."""
from dataclasses import dataclass

_ALPHABET = "23456789CFGHJMPQRVWX"
_BASE_SCORE = {"unverified": 20, "geocoded": 50, "customer_confirmed": 80, "driver_confirmed": 90}


def is_valid_plus_code(code: str) -> bool:
    """True for full or short Open Location Codes (e.g. 6FR6C8F7+2X or C8F7+2X)."""
    code = code.strip().upper()
    if code.count("+") != 1:
        return False
    head, tail = code.split("+")
    if not (2 <= len(tail) <= 3 or tail == "") or any(c not in _ALPHABET for c in tail):
        return False
    if len(head) not in (4, 6, 8) or any(c not in _ALPHABET for c in head):
        return False
    return True


_PAIR_RESOLUTIONS = (20.0, 1.0, 0.05, 0.0025, 0.000125)


def decode_plus_code(code: str) -> tuple[float, float] | None:
    """Centre point of a FULL plus code (8+ chars before '+'); short codes need a reference and return None."""
    code = code.strip().upper()
    if not is_valid_plus_code(code) or len(code.split("+")[0]) < 8:
        return None
    digits = code.replace("+", "")
    pairs = min(len(digits), 10) // 2
    lat, lng = -90.0, -180.0
    for i in range(pairs):
        lat += _ALPHABET.index(digits[2 * i]) * _PAIR_RESOLUTIONS[i]
        lng += _ALPHABET.index(digits[2 * i + 1]) * _PAIR_RESOLUTIONS[i]
    cell = _PAIR_RESOLUTIONS[pairs - 1]
    return lat + cell / 2, lng + cell / 2


def location_score(confidence: str | None, has_coordinates: bool, has_plus_code: bool, has_landmark: bool) -> int:
    """0-100 score: confidence level plus corroborating evidence (coordinates, plus code, landmark)."""
    score = _BASE_SCORE.get(confidence or "unverified", 20)
    score += 10 if has_coordinates else 0
    score += 5 if has_plus_code else 0
    score += 5 if has_landmark else 0
    return min(100, score)


def score_band(score: int) -> str:
    return "High" if score >= 70 else "Medium" if score >= 45 else "Low"


@dataclass(frozen=True)
class EffectiveLocation:
    address_text: str | None
    landmark: str | None
    delivery_notes: str | None
    latitude: float | None
    longitude: float | None
    plus_code: str | None
    recipient_available: bool | None
    confidence: str | None
    corrected: bool


def apply_corrections(stop, plan, corrections) -> EffectiveLocation:
    """Overlay corrections (oldest first) on the immutable original stop. The stop itself is never changed."""
    loc = {
        "address_text": stop.address_text if stop else None,
        "landmark": stop.landmark if stop else None,
        "delivery_notes": stop.delivery_notes if stop else None,
        "latitude": stop.latitude if stop else None,
        "longitude": stop.longitude if stop else None,
        "plus_code": plan.plus_code if plan else None,
        "recipient_available": stop.recipient_available if stop else None,
        "confidence": stop.location_confidence if stop else None,
    }
    for correction in corrections:
        for key in ("address_text", "landmark", "delivery_notes", "latitude", "longitude", "plus_code", "recipient_available"):
            value = getattr(correction, key)
            if value is not None:
                loc[key] = value
        if correction.location_confidence:
            loc["confidence"] = correction.location_confidence
    return EffectiveLocation(corrected=bool(corrections), **loc)
