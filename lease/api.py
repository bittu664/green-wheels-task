import re
from contextlib import asynccontextmanager
from time import monotonic
from uuid import uuid4

import psycopg
from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest
from psycopg_pool import PoolTimeout

from lease.domain import Fact
from lease.store import Conflict, get_lease, ingest, make_pool
from lease.telemetry import DURATION, REQUESTS, log

BUSINESS_ROUTES = {"/leases/events", "/leases/{driver_id}"}


@asynccontextmanager
async def lifespan(app):
    app.state.db = make_pool()
    try:
        yield
    finally:
        app.state.db.close()


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def observe(request, call_next):
    supplied = request.headers.get("x-request-id", "")
    request.state.request_id = supplied if re.fullmatch(r"[\w.-]{1,80}", supplied) else str(uuid4())
    started = monotonic()
    try:
        response = await call_next(request)
    except Exception as exc:
        log("unexpected_error", request_id=request.state.request_id, error=type(exc).__name__)
        response = Response(status_code=500)
    route = getattr(request.scope.get("route"), "path", "unmatched")
    status = response.status_code
    elapsed = monotonic() - started
    if route in BUSINESS_ROUTES:
        if status >= 500 or status == 429:
            outcome = "bad"
        elif status == 202 or (route == "/leases/{driver_id}" and status in (200, 404)):
            outcome = "good"
        else:
            outcome = "excluded"
        REQUESTS.labels(request.method, route, f"{status // 100}xx", outcome).inc()
        DURATION.labels(request.method, route, outcome).observe(elapsed)
    if route != "/metrics":
        log("http_request", request_id=request.state.request_id, route=route,
            method=request.method, driver_id=getattr(request.state, "driver_id", None),
            event_type=getattr(request.state, "event_type", None),
            event_id=getattr(request.state, "event_id", None),
            status_code=status, latency_ms=round(elapsed * 1000, 2))
    response.headers["x-request-id"] = request.state.request_id
    return response


def unavailable(request, exc):
    kind = "db_pool_timeout" if isinstance(exc, PoolTimeout) else "db_unavailable"
    log(kind, request_id=request.state.request_id, error=type(exc).__name__)
    return HTTPException(503, "Database temporarily unavailable")


@app.get("/live")
def live():
    return {"status": "live"}


@app.get("/health")
def health(request: Request):
    try:
        with request.app.state.db.connection() as conn:
            conn.execute("SELECT version FROM lease_sequence LIMIT 0")
    except (PoolTimeout, psycopg.Error) as exc:
        raise unavailable(request, exc) from exc
    return {"status": "ready"}


@app.get("/leases/{driver_id}")
def read_lease(driver_id: str, request: Request):
    request.state.driver_id = driver_id
    try:
        lease = get_lease(request.app.state.db, driver_id)
    except (PoolTimeout, psycopg.Error) as exc:
        raise unavailable(request, exc) from exc
    if lease is None:
        raise HTTPException(404, "Lease projection not found")
    return lease


@app.post("/leases/events", status_code=202)
def accept(fact: Fact, request: Request):
    request.state.driver_id = fact.driver_id
    request.state.event_type = fact.event_type
    request.state.event_id = fact.event_id
    try:
        version = ingest(request.app.state.db, fact, request.state.request_id)
    except Conflict as exc:
        raise HTTPException(409, "Event ID already used for a different fact") from exc
    except (PoolTimeout, psycopg.Error) as exc:
        raise unavailable(request, exc) from exc
    return {"event_id": fact.event_id, "version": version}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(REGISTRY), headers={"Content-Type": CONTENT_TYPE_LATEST})
