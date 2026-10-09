from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routebridge.config.settings import get_settings
from routebridge.db.session import create_db_and_tables
from routebridge.db.session import engine
from routebridge.db.seed import seed_reference_data
from routebridge.config.validation import validate_production_settings
from routebridge.workers.embedded import start_embedded_workers
from routebridge.db.health import validate_production_database
from routebridge.routes.orders import router as orders_router
from routebridge.routes.operations import router as operations_router
from routebridge.routes.reliability import router as reliability_router
from routebridge.routes.admin import router as admin_router
from routebridge.routes.imports import router as imports_router
from routebridge.routes.settlements import router as settlements_router
from routebridge.routes.system import router as system_router
from routebridge.routes.auth import router as auth_router
from routebridge.routes.webhooks import router as webhooks_router
from routebridge.routes.events import router as events_router
from routebridge.routes.planning import router as planning_router
from routebridge.routes.platform import router as platform_router
from routebridge.routes.portal import router as portal_router
from routebridge.routes.public import router as public_router
from routebridge.routes.reports import router as reports_router
from routebridge.routes.governance import router as governance_router
from routebridge.routes.intake import router as intake_router
from routebridge.routes.billing import router as billing_router
from routebridge.routes.delivery_codes import router as delivery_codes_router
from routebridge.routes.merchant_profiles import portal as merchant_profile_portal_router, staff as merchant_profile_router
from routebridge.routes.claims import portal as claims_portal_router, staff as claims_router
from routebridge.routes.driver import router as driver_router, staff_router as driver_staff_router
from routebridge.models.core import HealthResponse
from routebridge.models import core, orders  # noqa: F401
from routebridge.models import operations  # noqa: F401
from routebridge.models import reliability  # noqa: F401
from routebridge.models import catalog, workflows  # noqa: F401
from routebridge.models import webhooks  # noqa: F401
from routebridge.models import events  # noqa: F401
from routebridge.models import access  # noqa: F401
from routebridge.models import plans  # noqa: F401
from routebridge.observability import observe_requests
from routebridge.security import api_key_guard
from sqlmodel import Session

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_production_settings(settings)
    validate_production_database()
    if settings.environment in {"development", "test"}:
        create_db_and_tables()
    with Session(engine) as session:
        seed_reference_data(session)
    start_embedded_workers()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(api_key_guard)
app.middleware("http")(observe_requests)  # added last = outermost, so it also times rejected requests
app.include_router(orders_router, prefix=settings.api_v1_prefix)
app.include_router(operations_router, prefix=settings.api_v1_prefix)
app.include_router(reliability_router, prefix=settings.api_v1_prefix)
app.include_router(admin_router, prefix=settings.api_v1_prefix)
app.include_router(imports_router, prefix=settings.api_v1_prefix)
app.include_router(settlements_router, prefix=settings.api_v1_prefix)
app.include_router(system_router)
app.include_router(auth_router, prefix=settings.api_v1_prefix)
# before webhooks_router: its /webhooks/{provider} would otherwise swallow /webhooks/paystack
app.include_router(billing_router, prefix=settings.api_v1_prefix)
app.include_router(claims_router, prefix=settings.api_v1_prefix)
app.include_router(delivery_codes_router, prefix=settings.api_v1_prefix)
app.include_router(merchant_profile_router, prefix=settings.api_v1_prefix)
app.include_router(merchant_profile_portal_router, prefix=settings.api_v1_prefix)
app.include_router(claims_portal_router, prefix=settings.api_v1_prefix)
app.include_router(webhooks_router, prefix=settings.api_v1_prefix)
app.include_router(events_router, prefix=settings.api_v1_prefix)
app.include_router(planning_router, prefix=settings.api_v1_prefix)
app.include_router(platform_router, prefix=settings.api_v1_prefix)
app.include_router(portal_router, prefix=settings.api_v1_prefix)
app.include_router(public_router, prefix=settings.api_v1_prefix)
app.include_router(reports_router, prefix=settings.api_v1_prefix)
app.include_router(governance_router, prefix=settings.api_v1_prefix)
app.include_router(intake_router, prefix=settings.api_v1_prefix)
app.include_router(driver_router, prefix=settings.api_v1_prefix)
app.include_router(driver_staff_router, prefix=settings.api_v1_prefix)


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        environment=settings.environment,
    )
