"""
Financial sentiment scoring.

Primary: FinBERT (ProsusAI/finbert, Apache 2.0) — finance-specific BERT, ~430 MB local cache.
         https://github.com/ProsusAI/finBERT
Fallback: VADER (NLTK) — rule-based, ~2 MB, loads instantly when transformers unavailable.

FinBERT is trained on financial phrasebank + financial news; far outperforms VADER on
earnings calls, SEC filings, and financial headlines (F1 ~87% vs VADER ~72% on FinancialPhraseBank).
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone

import database

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FinBERT loader (primary)
# ---------------------------------------------------------------------------

_finbert_pipeline = None
_USE_FINBERT = False

try:
    from transformers import pipeline as hf_pipeline
    _HF_AVAILABLE = True
except ImportError:
    _HF_AVAILABLE = False
    logger.warning("transformers not installed — falling back to VADER. Run: pip install transformers")


def _get_finbert():
    global _finbert_pipeline, _USE_FINBERT
    if _finbert_pipeline is not None:
        return _finbert_pipeline
    if not _HF_AVAILABLE:
        return None
    try:
        logger.info("Loading FinBERT (ProsusAI/finbert) — first run downloads ~430 MB to ~/.cache/huggingface")
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
        model = AutoModelForSequenceClassification.from_pretrained(
            "ProsusAI/finbert",
            use_safetensors=True,  # avoids torch.load CVE-2025-32434 (safe format)
        )
        _finbert_pipeline = hf_pipeline(
            "text-classification",
            model=model,
            tokenizer=tokenizer,
            top_k=None,
            truncation=True,
            max_length=512,
            device=-1,
        )
        _USE_FINBERT = True
        logger.info("FinBERT loaded OK (safetensors)")
    except Exception as e:
        logger.warning("FinBERT load failed (%s) — falling back to VADER", e)
        _finbert_pipeline = None
    return _finbert_pipeline


# ---------------------------------------------------------------------------
# VADER fallback loader
# ---------------------------------------------------------------------------

_vader = None


def _get_vader():
    global _vader
    if _vader is None:
        import nltk
        nltk.download("vader_lexicon", quiet=True)
        from nltk.sentiment.vader import SentimentIntensityAnalyzer
        _vader = SentimentIntensityAnalyzer()
    return _vader


# ---------------------------------------------------------------------------
# Unified batch scorer
# ---------------------------------------------------------------------------

def _score_batch(texts: list[str]) -> list[dict]:
    """Returns list of {positive, negative, neutral} dicts. Uses FinBERT if available."""
    pipe = _get_finbert()

    if pipe is not None:
        # FinBERT: batch inference (faster than one-by-one)
        # Truncate to 512 tokens worth of chars (~2000 chars) before sending
        truncated = [t[:2000] for t in texts]
        try:
            raw_batches = pipe(truncated, batch_size=16)
            results = []
            for batch in raw_batches:
                # batch is a list of {label, score} dicts (top_k=None returns all 3)
                label_map = {item["label"].lower(): item["score"] for item in batch}
                results.append({
                    "positive": label_map.get("positive", 0.0),
                    "negative": label_map.get("negative", 0.0),
                    "neutral":  label_map.get("neutral",  0.0),
                })
            return results
        except Exception as e:
            logger.warning("FinBERT inference error (%s) — falling back to VADER for this batch", e)

    # VADER fallback
    sid = _get_vader()
    results = []
    for text in texts:
        s = sid.polarity_scores(text)
        results.append({
            "positive": s["pos"],
            "negative": s["neg"],
            "neutral":  s["neu"],
        })
    return results


def score_new_articles():
    """Score all unscored news articles that mention Tier 1+ tickers."""
    conn = database.get_connection()
    try:
        tier_rows = conn.execute(
            "SELECT ticker FROM ticker_universe WHERE active=1 AND tier>=1"
        ).fetchall()
        tier_symbols = {r["ticker"].split(".")[0] for r in tier_rows}

        rows = conn.execute("""
            SELECT id, headline, ticker_mentions, published_at
            FROM news_articles
            WHERE sentiment_done=0
            ORDER BY published_at DESC
            LIMIT 2000
        """).fetchall()
    finally:
        conn.close()

    if not rows:
        logger.debug("No new articles to score")
        return

    relevant = []
    for row in rows:
        mentions = json.loads(row["ticker_mentions"] or "[]")
        active_mentions = [m for m in mentions if m in tier_symbols]
        if active_mentions:
            relevant.append((row["id"], row["headline"], active_mentions, row["published_at"]))

    if not relevant:
        logger.debug("No articles mention active tickers")
        _mark_scored(conn=None, ids=[r[0] for r in rows])
        return

    logger.info("Scoring %d articles with VADER", len(relevant))
    texts = [r[1] for r in relevant]
    scores = _score_batch(texts)

    ticker_day_scores: dict[tuple, list[dict]] = defaultdict(list)
    for (art_id, headline, mentions, published_at), score in zip(relevant, scores):
        date = published_at[:10] if published_at else datetime.now(timezone.utc).date().isoformat()
        for symbol in mentions:
            ticker_day_scores[(symbol, date)].append(score)

    conn = database.get_connection()
    try:
        cur = conn.cursor()
        for (symbol, date), score_list in ticker_day_scores.items():
            avg_pos = sum(s["positive"] for s in score_list) / len(score_list)
            avg_neg = sum(s["negative"] for s in score_list) / len(score_list)
            avg_neu = sum(s["neutral"] for s in score_list) / len(score_list)
            composite = avg_pos - avg_neg
            cur.execute("""
                INSERT INTO sentiment_scores
                    (ticker, date, positive, negative, neutral, article_count, composite_score)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(ticker, date) DO UPDATE SET
                    positive=(positive * article_count + excluded.positive * excluded.article_count)
                              / (article_count + excluded.article_count),
                    negative=(negative * article_count + excluded.negative * excluded.article_count)
                              / (article_count + excluded.article_count),
                    neutral=(neutral * article_count + excluded.neutral * excluded.article_count)
                            / (article_count + excluded.article_count),
                    article_count=article_count + excluded.article_count,
                    composite_score=(composite_score * article_count + excluded.composite_score * excluded.article_count)
                                    / (article_count + excluded.article_count)
            """, (symbol, date, avg_pos, avg_neg, avg_neu, len(score_list), composite))

        ids = [r[0] for r in rows]
        cur.executemany("UPDATE news_articles SET sentiment_done=1 WHERE id=?", [(i,) for i in ids])
        conn.commit()
        logger.info("Sentiment done: %d ticker-days updated", len(ticker_day_scores))
    finally:
        conn.close()


def _mark_scored(conn, ids: list[int]):
    c = database.get_connection() if conn is None else conn
    try:
        c.executemany("UPDATE news_articles SET sentiment_done=1 WHERE id=?", [(i,) for i in ids])
        c.commit()
    finally:
        if conn is None:
            c.close()


def get_sentiment(ticker: str, days: int = 7) -> list[dict]:
    base = ticker.split(".")[0]
    conn = database.get_connection()
    try:
        rows = conn.execute("""
            SELECT date, positive, negative, neutral, composite_score, article_count
            FROM sentiment_scores
            WHERE ticker=?
            ORDER BY date DESC LIMIT ?
        """, (base, days)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
