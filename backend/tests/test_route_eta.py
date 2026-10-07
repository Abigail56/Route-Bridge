import httpx
import pytest

from routebridge.config.settings import get_settings
from routebridge.services import route_eta, tracking

LEKKI = (6.4474, 3.4723)
IKEJA = (6.6018, 3.3515)


@pytest.fixture(autouse=True)
def clean():
    settings = get_settings()
    old = (settings.route_provider, settings.route_api_key, route_eta._client)
    route_eta.reset()
    yield
    settings.route_provider, settings.route_api_key, route_eta._client = old
    route_eta.reset()


def use(handler, provider="osrm", key=""):
    settings = get_settings()
    settings.route_provider, settings.route_api_key = provider, key
    route_eta._client = httpx.Client(transport=httpx.MockTransport(handler))


def test_nothing_is_called_when_no_provider_is_set() -> None:
    use(lambda request: pytest.fail("must not call out"), provider="none")
    assert route_eta.travel_minutes(LEKKI, IKEJA) is None


def test_osrm_gives_minutes_by_road() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json={"code": "Ok", "routes": [{"duration": 1805.0}]})

    use(handler)
    assert route_eta.travel_minutes(LEKKI, IKEJA) == 30
    assert seen["path"].startswith("/route/v1/driving/3.472300,6.447400;3.351500,6.601800")  # longitude first, as OSRM wants


def test_mapbox_uses_the_traffic_profile_and_needs_a_key() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"routes": [{"duration": 2400}]})

    use(handler, provider="mapbox", key="")
    assert route_eta.travel_minutes(LEKKI, IKEJA) is None and "url" not in seen  # no key: not even attempted
    use(handler, provider="mapbox", key="pk.test")
    assert route_eta.travel_minutes(LEKKI, IKEJA) == 40
    assert "driving-traffic" in seen["url"] and "access_token=pk.test" in seen["url"]


def test_answers_are_remembered_briefly() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={"routes": [{"duration": 600}]})

    use(handler)
    assert route_eta.travel_minutes(LEKKI, IKEJA) == 10
    assert route_eta.travel_minutes((LEKKI[0] + 0.0001, LEKKI[1]), IKEJA) == 10  # a few metres further: same answer, no new call
    assert len(calls) == 1


def test_failures_return_none_and_the_circuit_stops_the_calls() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(500)

    use(handler)
    results = [route_eta.travel_minutes((6.4 + i / 100, 3.4), IKEJA) for i in range(8)]
    assert results == [None] * 8
    assert len(calls) == 4  # the breaker opened after 4 failures and the rest never went out


def test_garbage_and_no_route_answers_are_not_trusted() -> None:
    use(lambda request: httpx.Response(200, json={"code": "NoRoute", "routes": []}))
    assert route_eta.travel_minutes(LEKKI, IKEJA) is None


def test_tracking_prefers_the_road_time_and_falls_back_to_the_plain_estimate() -> None:
    plain = tracking.eta_minutes(tracking.haversine_km(LEKKI, IKEJA))
    use(lambda request: httpx.Response(200, json={"routes": [{"duration": 3600}]}))
    assert tracking.best_eta(LEKKI, IKEJA) == 60
    route_eta.reset()
    use(lambda request: httpx.Response(503))
    assert tracking.best_eta(LEKKI, IKEJA) == plain
