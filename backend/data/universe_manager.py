"""
Downloads and maintains the full stock universe:
  - US: NASDAQ FTP (nasdaqlisted.txt + otherlisted.txt) — ~8k tickers
  - India NSE: NSE EQUITY_L.csv — ~2k active equities
  - India BSE: BSE bhavcopy ZIP — ~5k tickers
Applies liquidity filter, assigns tiers 0/1/2.
"""

import io
import json
import logging
import ftplib
import time
import zipfile
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import requests
import yfinance as yf

import database
from config import (
    MIN_PRICE_USD, MIN_PRICE_INR, MIN_AVG_VOLUME_30D,
    TIER1_SIZE, TIER2_SIZE, DEEP_ANALYSIS_SIZE,
    YFINANCE_BATCH_SIZE, YFINANCE_BATCH_DELAY, YFINANCE_MAX_RETRIES,
)

logger = logging.getLogger(__name__)

NSE_EQUITY_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
BSE_BHAVCOPY_URL = "https://www.bseindia.com/download/BhavCopy/Equity/EQ{date}_CSV.ZIP"

HEADERS = {"User-Agent": "StockBot/1.0 research@stockbot.local"}


# ---------------------------------------------------------------------------
# Ticker list downloaders
# ---------------------------------------------------------------------------

def download_us_tickers() -> pd.DataFrame:
    """Fetch all US tickers from NASDAQ FTP directory files."""
    rows = []
    files = {
        "nasdaqlisted.txt": "NASDAQ",
        "otherlisted.txt": "NYSE/AMEX",
    }
    try:
        ftp = ftplib.FTP("ftp.nasdaqtrader.com", timeout=30)
        ftp.login()
        ftp.cwd("/SymbolDirectory")
        for filename, exchange_label in files.items():
            buf = io.BytesIO()
            ftp.retrbinary(f"RETR {filename}", buf.write)
            buf.seek(0)
            df = pd.read_csv(buf, sep="|")
            # Drop trailer line ("File Creation Time" row)
            df = df[~df.iloc[:, 0].astype(str).str.startswith("File")]
            if "Symbol" in df.columns:
                sym_col = "Symbol"
            elif "ACT Symbol" in df.columns:
                sym_col = "ACT Symbol"
            else:
                continue
            name_col = "Security Name" if "Security Name" in df.columns else df.columns[1]
            for _, row in df.iterrows():
                ticker = str(row[sym_col]).strip()
                if not ticker or ticker in ("nan", "Symbol"):
                    continue
                # Skip ETFs, preferred shares, warrants etc.
                if any(c in ticker for c in ["$", "^", "/"]):
                    continue
                rows.append({
                    "ticker": ticker,
                    "exchange": exchange_label,
                    "name": str(row.get(name_col, "")).strip(),
                    "sector": None,
                    "currency": "USD",
                })
        ftp.quit()
    except Exception as exc:
        logger.error("US FTP download failed: %s", exc)
    logger.info("Downloaded %d US tickers", len(rows))
    return pd.DataFrame(rows)


def download_nse_tickers() -> pd.DataFrame:
    """Fetch all NSE equity tickers."""
    try:
        resp = requests.get(NSE_EQUITY_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        df.columns = [c.strip() for c in df.columns]
        sym_col = "SYMBOL" if "SYMBOL" in df.columns else df.columns[0]
        name_col = "NAME OF COMPANY" if "NAME OF COMPANY" in df.columns else df.columns[1]
        rows = []
        for _, row in df.iterrows():
            sym = str(row[sym_col]).strip()
            if not sym or sym == "SYMBOL":
                continue
            rows.append({
                "ticker": f"{sym}.NS",
                "exchange": "NSE",
                "name": str(row.get(name_col, "")).strip(),
                "sector": None,
                "currency": "INR",
            })
        logger.info("Downloaded %d NSE tickers", len(rows))
        return pd.DataFrame(rows)
    except Exception as exc:
        logger.error("NSE download failed: %s", exc)
        return pd.DataFrame()


def download_bse_tickers() -> pd.DataFrame:
    """Fetch all BSE equity tickers from most recent bhavcopy."""
    rows = []
    # Try last 5 business days
    from pandas.tseries.offsets import BDay
    for delta in range(1, 6):
        dt = (pd.Timestamp.now() - BDay(delta)).strftime("%d%m%Y")
        url = BSE_BHAVCOPY_URL.format(date=dt)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code != 200:
                continue
            zf = zipfile.ZipFile(io.BytesIO(resp.content))
            csv_name = [n for n in zf.namelist() if n.endswith(".CSV")][0]
            df = pd.read_csv(zf.open(csv_name))
            df.columns = [c.strip() for c in df.columns]
            # BSE bhavcopy: SC_CODE, SC_NAME, SC_TYPE, ...
            if "SC_CODE" not in df.columns:
                continue
            # Only equity type
            if "SC_TYPE" in df.columns:
                df = df[df["SC_TYPE"].astype(str).str.strip() == "Q"]
            for _, row in df.iterrows():
                code = str(row["SC_CODE"]).strip()
                if not code:
                    continue
                rows.append({
                    "ticker": f"{code}.BO",
                    "exchange": "BSE",
                    "name": str(row.get("SC_NAME", "")).strip(),
                    "sector": None,
                    "currency": "INR",
                })
            logger.info("Downloaded %d BSE tickers from %s", len(rows), dt)
            break
        except Exception as exc:
            logger.warning("BSE bhavcopy %s failed: %s", dt, exc)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Liquidity filter
# ---------------------------------------------------------------------------

def _yf_batch_download(tickers: list[str], period: str, interval: str) -> pd.DataFrame:
    """Batch yfinance download with retries and rate limiting."""
    all_frames = []
    for i in range(0, len(tickers), YFINANCE_BATCH_SIZE):
        batch = tickers[i: i + YFINANCE_BATCH_SIZE]
        for attempt in range(YFINANCE_MAX_RETRIES):
            try:
                data = yf.download(
                    batch,
                    period=period,
                    interval=interval,
                    group_by="ticker",
                    auto_adjust=True,
                    progress=False,
                    threads=True,
                )
                all_frames.append(data)
                break
            except Exception as exc:
                wait = 2 ** attempt
                logger.warning("yfinance batch %d/%d attempt %d failed: %s. Retry in %ds",
                               i // YFINANCE_BATCH_SIZE + 1,
                               len(tickers) // YFINANCE_BATCH_SIZE + 1,
                               attempt + 1, exc, wait)
                time.sleep(wait)
        time.sleep(YFINANCE_BATCH_DELAY)
    return pd.concat(all_frames, axis=1) if all_frames else pd.DataFrame()


def apply_liquidity_filter(df_universe: pd.DataFrame) -> pd.DataFrame:
    """Fetch 30d daily data, compute avg volume and last price, filter."""
    tickers = df_universe["ticker"].tolist()
    logger.info("Fetching 30d data for %d tickers to apply liquidity filter...", len(tickers))
    data = _yf_batch_download(tickers, period="30d", interval="1d")

    results = []
    for ticker in tickers:
        try:
            if len(tickers) == 1:
                close = data["Close"]
                volume = data["Volume"]
            else:
                close = data[ticker]["Close"] if ticker in data.columns.get_level_values(0) else None
                volume = data[ticker]["Volume"] if ticker in data.columns.get_level_values(0) else None
            if close is None or close.empty:
                continue
            last_price = float(close.dropna().iloc[-1]) if not close.dropna().empty else 0
            avg_vol = float(volume.dropna().mean()) if volume is not None and not volume.dropna().empty else 0

            row = df_universe[df_universe["ticker"] == ticker].iloc[0]
            currency = row.get("currency", "USD")
            min_price = MIN_PRICE_INR if currency == "INR" else MIN_PRICE_USD

            if last_price >= min_price and avg_vol >= MIN_AVG_VOLUME_30D:
                results.append({
                    **row.to_dict(),
                    "last_price": last_price,
                    "avg_volume_30d": avg_vol,
                    "tier": 0,
                })
        except Exception as exc:
            logger.debug("Filter skip %s: %s", ticker, exc)

    filtered = pd.DataFrame(results)
    logger.info("Liquidity filter: %d → %d tickers pass", len(tickers), len(filtered))
    return filtered


# ---------------------------------------------------------------------------
# Tier classification
# ---------------------------------------------------------------------------

def update_tier_classification():
    """Rank all filtered tickers by momentum + volume surge → assign tiers."""
    conn = database.get_connection()
    try:
        df = pd.read_sql(
            "SELECT ticker, avg_volume_30d, last_price, exchange FROM ticker_universe WHERE active=1",
            conn
        )
        if df.empty:
            logger.warning("ticker_universe empty, skipping tier update")
            return

        # Get recent price change (1d) for momentum score
        tickers = df["ticker"].tolist()
        data = _yf_batch_download(tickers, period="5d", interval="1d")

        scores = []
        for ticker in tickers:
            try:
                if len(tickers) == 1:
                    close = data["Close"]
                    volume = data["Volume"]
                else:
                    close = data[ticker]["Close"] if ticker in data.columns.get_level_values(0) else None
                    volume = data[ticker]["Volume"] if ticker in data.columns.get_level_values(0) else None
                if close is None or len(close.dropna()) < 2:
                    scores.append({"ticker": ticker, "score": 0})
                    continue
                pct_chg = abs(float(close.dropna().pct_change().iloc[-1]))
                last_vol = float(volume.dropna().iloc[-1]) if volume is not None else 0
                avg_vol = df[df["ticker"] == ticker]["avg_volume_30d"].values[0]
                vol_ratio = last_vol / avg_vol if avg_vol > 0 else 0
                score = pct_chg * 0.5 + min(vol_ratio, 5) * 0.5
                scores.append({"ticker": ticker, "score": score})
            except Exception:
                scores.append({"ticker": ticker, "score": 0})

        score_df = pd.DataFrame(scores).sort_values("score", ascending=False).reset_index(drop=True)
        score_df["tier"] = 0
        score_df.loc[score_df.index < TIER1_SIZE, "tier"] = 1
        score_df.loc[score_df.index < DEEP_ANALYSIS_SIZE, "tier"] = 2

        cur = conn.cursor()
        cur.execute("UPDATE ticker_universe SET tier=0 WHERE active=1")
        for _, row in score_df.iterrows():
            cur.execute(
                "UPDATE ticker_universe SET tier=? WHERE ticker=?",
                (int(row["tier"]), row["ticker"])
            )
        conn.commit()
        logger.info("Tier update complete. Tier2=%d, Tier1=%d, Tier0=%d",
                    (score_df["tier"] == 2).sum(),
                    (score_df["tier"] == 1).sum(),
                    (score_df["tier"] == 0).sum())
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Main entry: full refresh
# ---------------------------------------------------------------------------

def refresh_universe():
    """
    Download all tickers from FTP/CSV, persist to DB WITHOUT yfinance calls.
    Price data is fetched gradually by the scheduler (fetch_tier0_eod).
    Liquidity filter runs later via update_tier_classification() once prices exist.
    """
    logger.info("Starting full universe refresh (no yfinance during seed)...")
    frames = []

    us = download_us_tickers()
    if not us.empty:
        frames.append(us)

    nse = download_nse_tickers()
    if not nse.empty:
        frames.append(nse)

    bse = download_bse_tickers()
    if not bse.empty:
        frames.append(bse)

    if not frames:
        logger.error("All ticker downloads failed")
        return

    raw = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["ticker"])
    logger.info("Raw universe: %d tickers — storing all, prices fetched by scheduler", len(raw))

    conn = database.get_connection()
    now = datetime.now(timezone.utc).isoformat()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE ticker_universe SET active=0")
        for _, row in raw.iterrows():
            cur.execute("""
                INSERT INTO ticker_universe
                    (ticker, exchange, name, sector, currency, tier, active, last_updated)
                VALUES (?,?,?,?,?,0,1,?)
                ON CONFLICT(ticker) DO UPDATE SET
                    exchange=excluded.exchange,
                    name=excluded.name,
                    currency=excluded.currency,
                    active=1,
                    last_updated=excluded.last_updated
            """, (
                row["ticker"], row["exchange"], row.get("name"),
                row.get("sector"), row.get("currency", "USD"), now,
            ))
        conn.commit()
        logger.info("Universe seeded: %d tickers stored (tier=0, prices TBD)", len(raw))
    finally:
        conn.close()

    # Immediately seed Tier 2 with known liquid majors so signals start working now
    _seed_known_tier2()


def _seed_known_tier2():
    """
    Hardcode top liquid US + India tickers as Tier 2 so signals work immediately
    without waiting for full price-based tier classification.
    """
    US_MAJORS = [
        "AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA","JPM","BAC","XOM",
        "BRK-B","JNJ","V","UNH","WMT","MA","HD","PG","CVX","MRK",
        "ABBV","LLY","AVGO","COST","PEP","KO","ADBE","CSCO","TMO","ACN",
        "MCD","CRM","ABT","DHR","TXN","NEE","PM","UPS","MS","GS",
        "RTX","BA","CAT","AMGN","SPGI","ISRG","BKNG","NOW","AMAT","ADP",
        "AMD","INTC","QCOM","NFLX","PYPL","SQ","SHOP","SNOW","PLTR","COIN",
        "CRWD","ZS","DDOG","MDB","NET","OKTA","UBER","LYFT","ABNB","DASH",
        "RBLX","RIVN","LCID","NIO","XPEV","LI","SOFI","HOOD","OPEN","AFRM",
        "SPY","QQQ","IWM","DIA","GLD","SLV","TLT","HYG",
    ]
    INDIA_MAJORS = [
        "TCS.NS","INFY.NS","RELIANCE.NS","HDFCBANK.NS","ICICIBANK.NS",
        "WIPRO.NS","HCLTECH.NS","SBIN.NS","BAJFINANCE.NS","BHARTIARTL.NS",
        "ASIANPAINT.NS","MARUTI.NS","TATAMOTORS.NS","AXISBANK.NS","LT.NS",
        "SUNPHARMA.NS","ULTRACEMCO.NS","TITAN.NS","NESTLEIND.NS","POWERGRID.NS",
        "NTPC.NS","ONGC.NS","COALINDIA.NS","JSWSTEEL.NS","TATASTEEL.NS",
        "ADANIENT.NS","ADANIPORTS.NS","HINDUNILVR.NS","DIVISLAB.NS","DRREDDY.NS",
        "CIPLA.NS","EICHERMOT.NS","HEROMOTOCO.NS","BAJAJ-AUTO.NS","M&M.NS",
        "GRASIM.NS","INDUSINDBK.NS","BPCL.NS","IOC.NS","TATACONSUM.NS",
    ]

    all_tier2 = US_MAJORS + INDIA_MAJORS
    conn = database.get_connection()
    now = datetime.now(timezone.utc).isoformat()
    try:
        cur = conn.cursor()
        for ticker in all_tier2:
            exchange = "NSE" if ticker.endswith(".NS") else ("BSE" if ticker.endswith(".BO") else "NASDAQ")
            currency = "INR" if ticker.endswith((".NS", ".BO")) else "USD"
            cur.execute("""
                INSERT INTO ticker_universe (ticker, exchange, currency, tier, active, last_updated)
                VALUES (?,?,?,2,1,?)
                ON CONFLICT(ticker) DO UPDATE SET tier=2, active=1, last_updated=excluded.last_updated
            """, (ticker, exchange, currency, now))
        conn.commit()
        logger.info("Seeded %d known liquid tickers as Tier 2 — signals will start immediately", len(all_tier2))
    finally:
        conn.close()


def get_tickers_by_tier(tier: int) -> list[str]:
    conn = database.get_connection()
    try:
        rows = conn.execute(
            "SELECT ticker FROM ticker_universe WHERE tier=? AND active=1", (tier,)
        ).fetchall()
        return [r["ticker"] for r in rows]
    finally:
        conn.close()


def get_all_active_tickers() -> list[str]:
    conn = database.get_connection()
    try:
        rows = conn.execute(
            "SELECT ticker FROM ticker_universe WHERE active=1"
        ).fetchall()
        return [r["ticker"] for r in rows]
    finally:
        conn.close()
