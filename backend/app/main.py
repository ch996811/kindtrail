"""Kindtrail API. Run: .venv/Scripts/python -m uvicorn app.main:app --app-dir backend --reload"""
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import Body, Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from . import ledger, review, service
from .config import Settings, load_settings
from .db import connect
from .llm import AIUnavailable, LLM, make_llm
from .paypal import PayPalClient, PayPalError
from .seed import DEMO_DIR, reset_demo, seed


class GiftIn(BaseModel):
    fund_code: str
    donor_name: str = Field(min_length=1, max_length=80)
    amount_cents: int = Field(gt=0, le=1_000_000)


class ApproveIn(BaseModel):
    approver: str = Field(default="Lin", min_length=1, max_length=80)


class LimitsIn(BaseModel):
    donor_words: str = Field(min_length=3, max_length=2000)


Category = Literal[tuple(review.CATEGORIES)]  # type: ignore[valid-type]


class PolicyIn(BaseModel):
    """A fund's limits after the donor has checked (and maybe edited) what the AI read."""
    region: str | None = Field(default=None, max_length=80)
    allowed: list[Category] = Field(default_factory=list, max_length=len(review.CATEGORIES))
    never: list[Category] = Field(default_factory=list, max_length=len(review.CATEGORIES))
    beneficiaries: str | None = Field(default=None, max_length=120)
    until: date | None = None

    def as_policy(self) -> dict[str, Any]:
        never = set(self.never) - review.ALWAYS_NEVER  # those are refused anyway; no need to store them
        return {"region": (self.region or "").strip() or None,
                "allowed": [c for c in review.CATEGORIES if c in set(self.allowed) - never - review.ALWAYS_NEVER],
                "never": [c for c in review.CATEGORIES if c in never],
                "beneficiaries": (self.beneficiaries or "").strip() or None,
                "until": self.until.isoformat() if self.until else None}


class FundIn(BaseModel):
    name: str = Field(min_length=3, max_length=80)
    donor_words: str = Field(min_length=3, max_length=2000)
    policy: PolicyIn


def _warm_up(provider: Any, paypal: Any) -> None:
    if hasattr(provider, "warm_up"):
        provider.warm_up()
    if isinstance(paypal, PayPalClient) and paypal.has_credentials:
        try:
            paypal.warm_up()
        except Exception:  # noqa: BLE001 - best effort; real calls report their own errors
            pass


RECEIPT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_RECEIPT_BYTES = 6 * 1024 * 1024


def create_app(settings: Settings | None = None, paypal: Any = None, conn: sqlite3.Connection | None = None,
               llm: LLM | None = None) -> FastAPI:
    settings = settings or load_settings()
    llm = llm or make_llm(settings.llm_provider, settings.gemini_api_key, settings.llm_daily_cap)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        setup = conn or connect(settings.db_path)  # creates the schema
        seed(setup, settings.partner_email, llm, demo_gifts=settings.demo_mode)
        if conn is None:
            setup.close()
        app.state.paypal = paypal or PayPalClient(settings.paypal_base_url, settings.paypal_client_id,
                                                  settings.paypal_client_secret)
        # Pay the slow first connections in the background, not on the first visitor's click.
        threading.Thread(target=_warm_up, args=(llm.provider, app.state.paypal), daemon=True).start()
        yield

    app = FastAPI(title="Kindtrail", lifespan=lifespan)

    @app.exception_handler(service.NotFound)
    async def _not_found(_: Request, exc: service.NotFound):
        return JSONResponse({"error": "not_found", "message": str(exc)}, status_code=404)

    @app.exception_handler(service.Conflict)
    async def _conflict(_: Request, exc: service.Conflict):
        return JSONResponse({"error": "conflict", "message": str(exc)}, status_code=409)

    @app.exception_handler(ledger.InsufficientFunds)
    async def _insufficient(_: Request, exc: ledger.InsufficientFunds):
        return JSONResponse({"error": "insufficient_funds", "message": str(exc),
                             "available_cents": exc.available_cents, "needed_cents": exc.needed_cents}, status_code=409)

    @app.exception_handler(AIUnavailable)
    async def _ai(_: Request, exc: AIUnavailable):
        return JSONResponse({"error": "ai_unavailable", "message": str(exc)}, status_code=503)

    @app.exception_handler(PayPalError)
    async def _paypal(_: Request, exc: PayPalError):
        return JSONResponse({"error": "paypal", "message": str(exc), "paypal_status": exc.status}, status_code=502)

    def db() -> Iterator[sqlite3.Connection]:
        """One connection per request, so concurrent requests never share a transaction."""
        if conn is not None:  # tests inject a shared in-memory database
            yield conn
            return
        c = connect(settings.db_path, init=False)
        try:
            yield c
        finally:
            c.close()

    def pp(request: Request):
        return request.app.state.paypal

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "paypal_env": settings.paypal_env}

    @app.get("/api/config")
    def public_config() -> dict[str, Any]:
        # The client id is public by design (the PayPal SDK needs it in the browser); the secret never leaves the server.
        return {"paypal_client_id": settings.paypal_client_id, "paypal_env": settings.paypal_env,
                "demo_mode": settings.demo_mode}

    @app.post("/api/demo/reset")
    def demo_reset(conn: sqlite3.Connection = Depends(db)):
        if not settings.demo_mode:
            raise service.NotFound("demo reset is only available in demo mode")
        reset_demo(conn)
        return {"ok": True}

    @app.get("/api/funds")
    def list_funds(conn: sqlite3.Connection = Depends(db)):
        return service.list_funds(conn)

    @app.post("/api/funds", status_code=201)
    def create_fund(body: FundIn, conn: sqlite3.Connection = Depends(db)):
        return service.create_fund(conn, name=body.name, donor_words=body.donor_words, policy=body.policy.as_policy())

    @app.get("/api/funds/{code}")
    def get_fund(code: str, conn: sqlite3.Connection = Depends(db)):
        return service.fund_summary(conn, code)

    @app.post("/api/gifts", status_code=201)
    def create_gift(body: GiftIn, request: Request, conn: sqlite3.Connection = Depends(db)):
        return service.create_gift(conn, pp(request), fund_code=body.fund_code,
                                   donor_name=body.donor_name, amount_cents=body.amount_cents)

    @app.get("/api/gifts/{gift_id}/impact")
    def gift_impact(gift_id: int, conn: sqlite3.Connection = Depends(db)):
        return service.gift_impact(conn, gift_id)

    @app.post("/api/gifts/{order_id}/capture")
    def capture_gift(order_id: str, request: Request, conn: sqlite3.Connection = Depends(db)):
        return service.capture_gift(conn, pp(request), order_id)

    @app.post("/api/limits/parse")
    def parse_limits(body: LimitsIn, conn: sqlite3.Connection = Depends(db)):
        return service.parse_limits(conn, llm, body.donor_words)

    @app.get("/api/limits/categories")
    def limit_categories():
        return service.categories()

    @app.post("/api/limits/preview")
    def preview_limits(body: PolicyIn, conn: sqlite3.Connection = Depends(db)):
        receipts = [(p.stem, p.read_bytes()) for p in sorted((DEMO_DIR / "receipts").glob("*.jpg"))]
        return service.preview_policy(conn, llm, body.as_policy(), receipts)

    @app.post("/api/requests", status_code=201)
    def create_request(fund_code: str = Form(...), partner_id: str = Form(...),
                       purpose: str = Form(..., min_length=1, max_length=120), receipt: UploadFile = File(...),
                       conn: sqlite3.Connection = Depends(db)):
        if receipt.content_type not in RECEIPT_TYPES:
            raise service.Conflict(f"receipt must be a JPEG, PNG or WebP photo, got {receipt.content_type}")
        image = receipt.file.read(MAX_RECEIPT_BYTES + 1)
        if len(image) > MAX_RECEIPT_BYTES:
            raise service.Conflict("receipt photo is larger than 6 MB")
        return service.create_request(conn, llm, fund_code=fund_code, partner_id=partner_id, purpose=purpose,
                                      image=image, mime=receipt.content_type)

    @app.get("/api/demo/receipts")
    def demo_receipts():
        return [{"name": p.stem, "url": f"/api/demo/receipts/{p.name}"} for p in sorted((DEMO_DIR / "receipts").glob("*.jpg"))]

    @app.get("/api/demo/receipts/{filename}")
    def demo_receipt(filename: str):
        path = (DEMO_DIR / "receipts" / filename).resolve()
        if path.parent != (DEMO_DIR / "receipts").resolve() or not path.is_file():
            raise service.NotFound(f"no demo receipt {filename}")
        return FileResponse(path, media_type="image/jpeg")

    @app.get("/api/requests/{request_id}/receipt")
    def get_receipt(request_id: str, conn: sqlite3.Connection = Depends(db)):
        data, mime = service.receipt_image(conn, request_id)
        return Response(data, media_type=mime, headers={"Cache-Control": "public, max-age=86400"})

    @app.get("/api/requests/{request_id}")
    def get_request(request_id: str, conn: sqlite3.Connection = Depends(db)):
        return service.request_detail(conn, request_id)

    @app.post("/api/requests/{request_id}/approve")
    def approve(request_id: str, request: Request, body: ApproveIn | None = None,
                conn: sqlite3.Connection = Depends(db)):
        return service.approve_request(conn, pp(request), request_id, (body or ApproveIn()).approver)

    @app.post("/api/requests/{request_id}/refresh")
    def refresh(request_id: str, request: Request, conn: sqlite3.Connection = Depends(db)):
        return service.refresh_payout(conn, pp(request), request_id)

    @app.get("/api/reconcile")
    def reconcile(request: Request, days: int = 7, conn: sqlite3.Connection = Depends(db)):
        end = datetime.now(timezone.utc) - timedelta(seconds=5)
        start = end - timedelta(days=max(1, min(days, 31)))
        gifts = [{"gift_id": g["id"], "capture_id": g["paypal_capture_id"], "amount_cents": g["amount_cents"],
                  "fund_code": g["fund_code"], "source": g["source"]}
                 for g in conn.execute("SELECT * FROM gifts WHERE status = 'captured'")]
        payouts = [{"request_id": p["request_id"], "transaction_id": p["transaction_id"], "amount_cents": p["amount_cents"]}
                   for p in conn.execute("SELECT * FROM payouts")]
        result = ledger.reconcile(gifts, payouts, pp(request).search_transactions(start, end))
        result["window"] = {"start": start.isoformat(), "end": end.isoformat()}
        result["note"] = "PayPal can take up to 3 hours to list a new transaction in Transaction Search."
        return result

    @app.post("/api/webhooks/paypal")
    def paypal_webhook(request: Request, event: dict[str, Any] = Body(...), conn: sqlite3.Connection = Depends(db)):
        verified = False
        if settings.paypal_webhook_id:
            try:
                verified = pp(request).verify_webhook(webhook_id=settings.paypal_webhook_id,
                                                      headers=dict(request.headers), event=event)
            except PayPalError:
                verified = False
        return {"result": service.handle_webhook(conn, event, verified)}

    dist = Path(settings.frontend_dist).resolve()
    if dist.is_dir():
        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str):
            # Built assets are served as files; any other path is a page of the single-page app.
            if path.startswith("api/"):
                raise service.NotFound(f"no API route /{path}")
            file = (dist / path).resolve()
            if path and file.is_file() and dist in file.parents:
                return FileResponse(file)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
