"""Watchlist CRUD routes.

Reads and writes storage/watchlist.json.
Returns HTML fragments for HTMX swaps.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

WATCHLIST_PATH = Path(__file__).resolve().parents[2] / "storage" / "watchlist.json"
TEMPLATES_PATH = Path(__file__).resolve().parents[1] / "templates"

router    = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_PATH))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load() -> list[str]:
    if not WATCHLIST_PATH.exists():
        return []
    return json.loads(WATCHLIST_PATH.read_text())["stocks"]


def _save(stocks: list[str]) -> None:
    WATCHLIST_PATH.write_text(json.dumps({"stocks": stocks}, indent=2))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/stocks/add", response_class=HTMLResponse)
async def add_stock(request: Request, stock_id: str = Form(...)):
    """Add a stock to the watchlist and return the updated list fragment."""
    stock_id = stock_id.strip().upper()
    stocks   = _load()

    if stock_id and stock_id not in stocks:
        stocks.append(stock_id)
        _save(stocks)

    return templates.TemplateResponse(
        request, "partials/watchlist.html", {"stocks": stocks}
    )


@router.delete("/stocks/{stock_id}", response_class=HTMLResponse)
async def remove_stock(request: Request, stock_id: str):
    """Remove a stock from the watchlist and return the updated list fragment."""
    stocks = [s for s in _load() if s != stock_id.upper()]
    _save(stocks)

    return templates.TemplateResponse(
        request, "partials/watchlist.html", {"stocks": stocks}
    )
