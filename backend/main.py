"""FastAPI application entry point."""

import logging
import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure backend/ is on the path when running directly
sys.path.insert(0, os.path.dirname(__file__))

import database
from api.routes import router
from scheduler import create_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="StockBot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
async def startup():
    import threading

    logger.info("Initializing database...")
    database.init_db()

    try:
        from graph.neo4j_builder import init_graph
        init_graph()
    except Exception as exc:
        logger.warning("Neo4j init failed (will retry): %s", exc)

    logger.info("Starting scheduler...")
    scheduler = create_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler

    # Trigger GNN training if no checkpoint exists
    def _try_gnn_train():
        import time
        time.sleep(15)  # let price data settle first
        try:
            from graph.gnn_model import train as gnn_train, MODEL_PATH
            if not os.path.exists(MODEL_PATH):
                logger.info("No GNN checkpoint found — training now")
                gnn_train()
            else:
                logger.info("GNN checkpoint exists — skipping startup train")
        except Exception as exc:
            logger.warning("Startup GNN train failed: %s", exc)

    # Trigger Neo4j graph build if empty
    def _try_graph_update():
        import time
        time.sleep(5)
        try:
            from neo4j import GraphDatabase
            from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
            drv = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            with drv.session() as sess:
                count = sess.run("MATCH (s:Stock) RETURN count(s) AS n").single()["n"]
            drv.close()
            if count == 0:
                logger.info("Neo4j empty — running full graph update")
                from graph.neo4j_builder import run_full_graph_update
                run_full_graph_update()
            else:
                logger.info("Neo4j has %d stock nodes — skipping startup sync", count)
        except Exception as exc:
            logger.warning("Startup Neo4j graph update failed: %s", exc)

    threading.Thread(target=_try_gnn_train, daemon=True).start()
    threading.Thread(target=_try_graph_update, daemon=True).start()

    logger.info("StockBot API ready")


@app.on_event("shutdown")
async def shutdown():
    if hasattr(app.state, "scheduler"):
        app.state.scheduler.shutdown(wait=False)


@app.get("/")
def root():
    return {"service": "StockBot API", "docs": "/docs"}
