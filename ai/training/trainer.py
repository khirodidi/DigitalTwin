# ai/training/trainer.py — APScheduler: nightly retrain + hourly drift check
import logging
from datetime import datetime
from pathlib import Path
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron      import CronTrigger

logger     = logging.getLogger(__name__)
MODEL_DIR  = Path("models")
MIN_DAYS   = 7
PSI_THRESH = 0.20

class AITrainer:
    def __init__(self, engine):
        self._engine    = engine
        self._scheduler = AsyncIOScheduler()
        MODEL_DIR.mkdir(exist_ok=True)

    def start_scheduler(self):
        self._scheduler.add_job(self._retrain_all,  CronTrigger(hour=2, minute=0), id="nightly",     replace_existing=True)
        self._scheduler.add_job(self._check_drift,  CronTrigger(minute=0),          id="drift_check", replace_existing=True)
        self._scheduler.start()
        logger.info("AI training scheduler started (nightly 02:00 + hourly drift).")

    def stop_scheduler(self):
        self._scheduler.shutdown(wait=False)

    async def _retrain_all(self):
        logger.info(f"[AITrainer] Nightly retraining — {datetime.utcnow()}")
        if not self._has_enough_data():
            logger.info("[AITrainer] Not enough data yet."); return
        await self._run("movement");  await self._run("evacuation"); await self._run("monitor")
        self._reload()

    async def _run(self, model: str):
        try:
            if model == "movement":
                from ai.training.movement   import train_movement_model
                train_movement_model(model_path=str(MODEL_DIR/"movement_lstm.pt"))
            elif model == "evacuation":
                from ai.training.evacuation import train_danger_model
                train_danger_model(model_path=str(MODEL_DIR/"danger_xgb.joblib"))
            elif model == "monitor":
                from ai.training.monitor    import train_monitor_models
                train_monitor_models(model_dir=str(MODEL_DIR))
            logger.info(f"[AITrainer] {model} retrained.")
        except Exception as e:
            logger.error(f"[AITrainer] {model} failed: {e}", exc_info=True)

    async def _check_drift(self):
        try:
            from ai.training.drift import compute_psi
            psi = compute_psi()
            if psi > PSI_THRESH:
                logger.warning(f"[AITrainer] Drift PSI={psi:.3f} > {PSI_THRESH} — retraining.")
                await self._retrain_all()
        except Exception as e:
            logger.debug(f"[AITrainer] Drift check: {e}")

    def _reload(self):
        if self._engine and hasattr(self._engine, "reload_ai_models"):
            self._engine.reload_ai_models()
            logger.info("[AITrainer] Engine models reloaded.")

    def _has_enough_data(self) -> bool:
        try:
            from persistence.postgres import get_conn
            conn = get_conn()
            with conn.cursor() as cur:
                cur.execute("SELECT MIN(timestamp) FROM env_readings")
                oldest = cur.fetchone()[0]
            if oldest is None: return False
            return (datetime.utcnow() - oldest.replace(tzinfo=None)).days >= MIN_DAYS
        except Exception: return False
