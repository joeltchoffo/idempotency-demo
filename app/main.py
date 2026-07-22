from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .store import build_store


app = FastAPI(title="Idempotency Demo API", version="1.0.0")
store = build_store()


class Item(BaseModel):
    sku: str = Field(..., examples=["sku_abc"])
    qty: int = Field(..., ge=1, examples=[1])
    unit_price_cents: int = Field(..., ge=0, examples=[1999])


class OrderRequest(BaseModel):
    customer_id: str = Field(..., examples=["cust_123"])
    currency: str = Field(..., min_length=3, max_length=3, examples=["EUR"])
    amount_cents: int = Field(..., ge=0, examples=[1999])
    items: Optional[List[Item]] = None
    note: Optional[str] = None


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _hash_request(order: OrderRequest) -> str:
    payload = order.model_dump()
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/orders", status_code=201)
def create_order(
    order: OrderRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    if not idempotency_key:
        raise HTTPException(
            status_code=400,
            detail="Missing Idempotency-Key header. For the demo, it is required to prevent duplicates on retries.",
        )

    request_hash = _hash_request(order)
    response_body = {
        "order_id": f"ord_{uuid4().hex[:12]}",
        "status": "created",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "customer_id": order.customer_id,
        "currency": order.currency,
        "amount_cents": order.amount_cents,
        "request_hash": request_hash,
    }

    stored, created = store.put_if_absent(
        key=idempotency_key,
        request_hash=request_hash,
        status_code=201,
        response_json=response_body,
    )

    if stored.request_hash != request_hash:
        raise HTTPException(
            status_code=409,
            detail="Idempotency-Key already used with a different request body.",
        )

    return JSONResponse(
        status_code=stored.status_code,
        content=stored.response_json,
        headers={
            "Idempotency-Key": idempotency_key,
            "Idempotency-Replayed": "false" if created else "true",
            "Idempotency-Request-Hash": stored.request_hash,
        },
    )
