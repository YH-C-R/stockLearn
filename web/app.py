"""FastAPI application entry point.

Run from the project root:
    uvicorn web.app:app --reload

All existing analysis modules are imported via their normal package paths
because the project root is on sys.path when uvicorn is started from there.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from web.routes.analysis import router as analysis_router
from web.routes.backtest import router as backtest_router
from web.routes.chart import router as chart_router
from web.routes.stocks import router as stocks_router

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR       = Path(__file__).resolve().parent
TEMPLATES_DIR  = BASE_DIR / "templates"
STATIC_DIR     = BASE_DIR / "static"
WATCHLIST_PATH = BASE_DIR.parent / "storage" / "watchlist.json"

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Stock Analysis Tool")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app.include_router(analysis_router)
app.include_router(backtest_router)
app.include_router(chart_router)
app.include_router(stocks_router)


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

def _load_watchlist() -> list[str]:
    if not WATCHLIST_PATH.exists():
        return []
    return json.loads(WATCHLIST_PATH.read_text())["stocks"]


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    stocks = _load_watchlist()
    return templates.TemplateResponse(
        request, "index.html", {"stocks": stocks}
    )


@app.get("/stock/{stock_id}", response_class=HTMLResponse)
async def stock_detail(request: Request, stock_id: str):
    return templates.TemplateResponse(
        request, "stock.html", {"stock_id": stock_id.upper()}
    )
