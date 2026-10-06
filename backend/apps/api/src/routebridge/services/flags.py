"""Runtime feature switches (ROUTEBRIDGE_FEATURE_FLAGS='{"masked_calls": false}'), so risky or vendor-dependent
features can be turned off per environment or during a canary without a deploy."""
from routebridge.config.settings import get_settings

DEFAULTS: dict[str, bool] = {
    "customer_corrections": True,  # customers may correct their delivery location from the tracking page
    "whatsapp": True,  # use the WhatsApp channel when configured (SMS fallback is always on)
    "masked_calls": True,  # driver -> customer bridged calls and relayed messages
    "geocoding": True,  # server-side geocoding of addresses
    "driver_photo_uploads": True,
}


def enabled(name: str) -> bool:
    return bool(get_settings().feature_flags.get(name, DEFAULTS.get(name, False)))


def snapshot() -> dict[str, bool]:
    return {name: enabled(name) for name in sorted({*DEFAULTS, *get_settings().feature_flags})}
