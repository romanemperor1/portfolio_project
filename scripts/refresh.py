#!/usr/bin/env python3
"""
Hunch Portfolio — Price Refresh & Snapshot

Runs from GitHub Actions on a schedule (and on manual trigger).
Reads data/portfolio_state.json, fetches fresh prices from Yahoo Finance
(plus a small scrape for KCB which isn't on Yahoo), appends a new snapshot,
and writes the JSON back. The workflow then commits the change.

No external dependencies — Python stdlib only, so the Action job is fast.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = REPO_ROOT / "data" / "portfolio_state.json"

UA = (
    "Mozilla/5.0 (compatible; HunchPortfolioBot/1.0; "
    "+https://github.com/) AppleWebKit/537.36"
)

# Tickers Yahoo returns in non-USD that need FX conversion to USD
TICKER_FX_DIVISOR = {
    "IVN.TO": "CAD=X",
}

# Tickers we can't fetch from Yahoo — handled specially below
NOT_ON_YAHOO = {"KCB"}


# ---------------------------------------------------------------------- helpers
def fetch_yahoo(symbol: str, retries: int = 2) -> dict | None:
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.parse.quote(symbol)}?interval=1d&range=5d"
    )
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read())
                result = data.get("chart", {}).get("result")
                if not result:
                    return None
                return result[0]["meta"]
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    print(f"  fetch_yahoo({symbol}) failed after retries: {last_err}", file=sys.stderr)
    return None


def fetch_kcb_kes() -> float | None:
    """KCB Group NSE price in KES. Best-effort scrape from afx.kwayisi.org."""
    try:
        req = urllib.request.Request(
            "https://afx.kwayisi.org/nse/kcb.html", headers={"User-Agent": UA}
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", errors="ignore")
    except Exception as e:  # noqa: BLE001
        print(f"  fetch_kcb_kes failed: {e}", file=sys.stderr)
        return None

    # Look for the "Price" cell in the company quote block
    m = re.search(r"Price[^<]*</[^>]+>\s*<[^>]+>\s*([\d.]+)\s*<", html)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    # Fallback: any KES-style decimal near the top
    m = re.search(r"\b(\d{2,3}\.\d{2})\b", html)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def round2(n: float) -> float:
    return round(n * 100) / 100


# ---------------------------------------------------------------------- main
def main() -> int:
    state = json.loads(STATE_FILE.read_text())
    positions = [p for p in state.get("positions", []) if p.get("active", True)]
    if not positions:
        print("No active positions — nothing to refresh.")
        return 0

    last_snapshot_prices = (
        state["snapshots"][-1]["prices"] if state.get("snapshots") else {}
    )

    prices: dict[str, float] = {}
    errors: list[str] = []

    # FX rates first (so we can convert)
    fx: dict[str, float] = {}
    fx_syms = set(TICKER_FX_DIVISOR.values()) | {"KES=X"}
    for sym in fx_syms:
        meta = fetch_yahoo(sym)
        if meta and meta.get("regularMarketPrice"):
            fx[sym] = meta["regularMarketPrice"]
        else:
            errors.append(f"FX {sym}: unavailable")
        time.sleep(0.4)

    # Position tickers
    for p in positions:
        ticker = p["ticker"]
        if ticker in NOT_ON_YAHOO:
            continue  # handled below
        meta = fetch_yahoo(ticker)
        time.sleep(0.4)
        if not meta or meta.get("regularMarketPrice") is None:
            errors.append(f"{ticker}: no quote, using last-known")
            prices[ticker] = last_snapshot_prices.get(ticker, p["entryPrice"])
            continue
        price = meta["regularMarketPrice"]
        fx_sym = TICKER_FX_DIVISOR.get(ticker)
        if fx_sym:
            if fx_sym in fx:
                price = price / fx[fx_sym]
            else:
                errors.append(f"{ticker}: FX {fx_sym} missing, using last-known")
                prices[ticker] = last_snapshot_prices.get(ticker, p["entryPrice"])
                continue
        prices[ticker] = price

    # KCB special-case
    kcb_kes = fetch_kcb_kes()
    if kcb_kes and fx.get("KES=X"):
        prices["KCB"] = kcb_kes / fx["KES=X"]
    else:
        errors.append("KCB: scrape failed, using last-known")
        prices["KCB"] = last_snapshot_prices.get("KCB", 0.5132)

    # SPY benchmark
    spy_meta = fetch_yahoo("SPY")
    prices["SPY"] = (
        spy_meta["regularMarketPrice"] if spy_meta else last_snapshot_prices.get("SPY", 750.33)
    )

    # ----- Compute totals
    value = sum(prices[p["ticker"]] * p["shares"] for p in positions)
    invested = sum(p["entryPrice"] * p["shares"] for p in positions)
    spy_bench = sum(
        ((p["entryPrice"] * p["shares"]) / p["spyEntryPrice"]) * prices["SPY"]
        for p in positions
    )

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    snapshot = {
        "date": now,
        "portfolioValue": round2(value),
        "totalInvested": round2(invested),
        "spyBenchmarkValue": round2(spy_bench),
        "prices": {k: round(v, 6) for k, v in prices.items()},
    }

    state.setdefault("snapshots", []).append(snapshot)
    state["lastRefresh"] = now

    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")

    # ----- Console log (visible in Actions log)
    pnl = value - invested
    pnl_pct = (pnl / invested) * 100 if invested else 0
    spy_pnl_pct = (spy_bench - invested) / invested * 100 if invested else 0
    print(f"Snapshot {now}")
    print(f"  Portfolio value: ${value:,.2f}")
    print(f"  Total invested:  ${invested:,.2f}")
    print(f"  P&L:             ${pnl:+,.2f} ({pnl_pct:+.2f}%)")
    print(f"  vs SPY (dollar-weighted): {pnl_pct - spy_pnl_pct:+.2f} pp")
    print(f"  Snapshots total: {len(state['snapshots'])}")
    if errors:
        print("  Notes:")
        for e in errors:
            print(f"    - {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
