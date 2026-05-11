"""
World Bank macro economic data fetcher. No API key needed.
License: World Bank data is CC BY 4.0 — free for any use with attribution.
API: https://datahelpdesk.worldbank.org/knowledgebase/articles/898581

Fetches: GDP growth, inflation (CPI), interest rates, unemployment for US + major economies.
Used as macro regime filter in signal engine:
  - High GDP growth + low inflation = risk-on (amplify buy signals)
  - Recession + high inflation (stagflation) = risk-off (dampen signals)
"""

import logging
import time
from datetime import datetime, timezone

import requests

import database

logger = logging.getLogger(__name__)

WB_API = "https://api.worldbank.org/v2"
HEADERS = {"User-Agent": "StockBot/1.0 research@stockbot.local"}

# World Bank indicator codes (all free, no auth)
INDICATORS = {
    "gdp_growth":     "NY.GDP.MKTP.KD.ZG",   # GDP growth (annual %)
    "inflation_cpi":  "FP.CPI.TOTL.ZG",       # Inflation, CPI (annual %)
    "unemployment":   "SL.UEM.TOTL.ZS",        # Unemployment, total (% of labor force)
    "current_account":"BN.CAB.XOKA.GD.ZS",     # Current account balance (% of GDP)
}

COUNTRIES = {
    "US": "United States",
    "CN": "China",
    "EU": "Euro Area",  # aggregated
    "JP": "Japan",
    "IN": "India",
}


def _fetch_indicator(country: str, indicator: str, years: int = 5) -> list[dict]:
    """Fetch World Bank indicator data for a country."""
    url = f"{WB_API}/country/{country}/indicator/{indicator}"
    params = {
        "format": "json",
        "mrv": years,    # most recent values
        "per_page": years,
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if len(data) < 2 or not data[1]:
            return []
        return [
            {"year": item.get("date"), "value": item.get("value")}
            for item in data[1]
            if item.get("value") is not None
        ]
    except Exception as exc:
        logger.debug("World Bank %s/%s failed: %s", country, indicator, exc)
        return []


def fetch_macro_data():
    """Fetch all macro indicators for all tracked countries."""
    _ensure_table()
    conn = database.get_connection()
    cur = conn.cursor()
    saved = 0

    for country_code in COUNTRIES:
        for ind_name, ind_code in INDICATORS.items():
            rows = _fetch_indicator(country_code, ind_code, years=5)
            for row in rows:
                if row["value"] is None:
                    continue
                try:
                    cur.execute("""
                        INSERT OR REPLACE INTO macro_indicators
                            (country, indicator, year, value, updated_at)
                        VALUES (?,?,?,?,?)
                    """, (
                        country_code, ind_name, row["year"],
                        round(float(row["value"]), 4),
                        datetime.now(timezone.utc).isoformat(),
                    ))
                    saved += 1
                except Exception:
                    pass
            time.sleep(0.2)

    conn.commit()
    conn.close()
    logger.info("World Bank macro: saved %d indicator rows", saved)
    return saved


def get_macro_regime() -> dict:
    """
    Assess current macro regime from latest World Bank data.
    Returns: {regime, score, gdp_growth, inflation, signal_mult}

    Regimes:
      "goldilocks"    — GDP up, inflation low   → risk-on,  mult=1.15
      "overheating"   — GDP up, inflation high  → cautious, mult=0.95
      "stagflation"   — GDP down, inflation up  → risk-off, mult=0.75
      "recession"     — GDP down, inflation low → defensive, mult=0.85
      "unknown"       — insufficient data       → neutral,  mult=1.0
    """
    _ensure_table()
    conn = database.get_connection()
    try:
        gdp_row = conn.execute("""
            SELECT value, year FROM macro_indicators
            WHERE country='US' AND indicator='gdp_growth'
            ORDER BY year DESC LIMIT 1
        """).fetchone()

        inf_row = conn.execute("""
            SELECT value, year FROM macro_indicators
            WHERE country='US' AND indicator='inflation_cpi'
            ORDER BY year DESC LIMIT 1
        """).fetchone()

        unem_row = conn.execute("""
            SELECT value FROM macro_indicators
            WHERE country='US' AND indicator='unemployment'
            ORDER BY year DESC LIMIT 1
        """).fetchone()
    finally:
        conn.close()

    if not gdp_row or not inf_row:
        return {"regime": "unknown", "score": 0.0, "signal_mult": 1.0}

    gdp = float(gdp_row["value"])
    inf = float(inf_row["value"])
    unem = float(unem_row["value"]) if unem_row else 5.0

    gdp_up = gdp > 2.0
    inf_low = inf < 3.0

    if gdp_up and inf_low:
        regime = "goldilocks"
        score = 0.8
        mult = 1.15
    elif gdp_up and not inf_low:
        regime = "overheating"
        score = 0.2
        mult = 0.95
    elif not gdp_up and not inf_low:
        regime = "stagflation"
        score = -0.8
        mult = 0.75
    else:  # GDP down, inflation low
        regime = "recession"
        score = -0.4
        mult = 0.85

    return {
        "regime": regime,
        "score": score,
        "gdp_growth_pct": gdp,
        "inflation_pct": inf,
        "unemployment_pct": unem,
        "signal_mult": mult,
        "data_year": gdp_row["year"],
        "interpretation": f"GDP={gdp:.1f}%, CPI={inf:.1f}% → {regime.upper()}",
    }


def _ensure_table():
    conn = database.get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS macro_indicators (
                country TEXT NOT NULL,
                indicator TEXT NOT NULL,
                year TEXT NOT NULL,
                value REAL,
                updated_at TEXT,
                PRIMARY KEY (country, indicator, year)
            )
        """)
        conn.commit()
    finally:
        conn.close()
