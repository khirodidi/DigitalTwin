# =============================================================================
# ai/training/trainer.py
# Periodic AI model retraining using APScheduler.
# Trains all three models nightly (or on drift detection).
# Reloads models into the inference engine after training.
# =============================================================================

import logging
from datetime import datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron      import CronTrigger

logger = logging.getLogger(__name__)

MODEL_DIR      = Path("models")
MIN_DAYS_DATA  = 7      # minimum days before training starts
DRIFT_PSI_THRESHOLD = 0.2


class AITrainer:
    def __init__(self, engine):
        self._engine    = engine
        self._scheduler = AsyncIOScheduler()
        MODEL_DIR.mkdir(exist_ok=True)

    def start_scheduler(self):
        # Nightly retraining at 02:00
        self._scheduler.add_job(
            self._retrain_all,
            CronTrigger(hour=2, minute=0),
            id       = "nightly_retrain",
            name     = "Nightly AI model retraining",
            replace_existing = True,
        )
        # Drift check every hour
        self._scheduler.add_job(
            self._check_drift,
            CronTrigger(minute=0),
            id       = "hourly_drift_check",
            name     = "Hourly drift detection",
            replace_existing = True,
        )
        self._scheduler.start()
        logger.info("AI training scheduler started.")

    def stop_scheduler(self):
        self._scheduler.shutdown(wait=False)

    # ── Retraining jobs ────────────────────────────────────────────────────────

    async def _retrain_all(self):
        logger.info(f"[AITrainer] Starting nightly retraining — {datetime.utcnow()}")
        if not self._has_enough_data():
            logger.info("[AITrainer] Not enough data yet — skipping.")
            return

        await self._retrain_movement_model()
        await self._retrain_evacuation_model()
        await self._retrain_monitor_models()
        self._reload_models()
        logger.info("[AITrainer] Retraining complete — models reloaded.")

    async def _retrain_movement_model(self):
        """Retrain LSTM movement optimiser on latest location_events."""
        try:
            from ai.training.movement import train_movement_model
            train_movement_model(
                days       = 30,
                model_path = str(MODEL_DIR / "movement_lstm.pt"),
            )
            logger.info("[AITrainer] Movement model retrained.")
        except Exception as e:
            logger.error(f"[AITrainer] Movement retraining failed: {e}")

    async def _retrain_evacuation_model(self):
        """Retrain XGBoost danger score predictor on env_readings + incident labels."""
        try:
            from ai.training.evacuation import train_danger_model
            train_danger_model(
                days       = 90,
                model_path = str(MODEL_DIR / "danger_xgb.joblib"),
            )
            logger.info("[AITrainer] Evacuation danger model retrained.")
        except Exception as e:
            logger.error(f"[AITrainer] Evacuation retraining failed: {e}")

    async def _retrain_monitor_models(self):
        """Retrain LSTM autoencoder, forecaster, and failure predictor."""
        try:
            from ai.training.monitor import train_monitor_models
            train_monitor_models(
                days        = 30,
                model_dir   = str(MODEL_DIR),
            )
            logger.info("[AITrainer] Monitor models retrained.")
        except Exception as e:
            logger.error(f"[AITrainer] Monitor retraining failed: {e}")

    async def _check_drift(self):
        """Check for feature distribution drift — trigger retraining if needed."""
        try:
            from ai.training.drift import compute_psi
            psi = compute_psi(days_baseline=30, days_current=7)
            if psi > DRIFT_PSI_THRESHOLD:
                logger.warning(f"[AITrainer] Drift detected (PSI={psi:.3f}) — triggering retraining.")
                await self._retrain_all()
        except Exception as e:
            logger.debug(f"[AITrainer] Drift check skipped: {e}")

    def _reload_models(self):
        """Tell the inference engine to reload all AI models from disk."""
        if self._engine and hasattr(self._engine, "reload_ai_models"):
            self._engine.reload_ai_models()
            logger.info("[AITrainer] Inference engine reloaded models.")

    def _has_enough_data(self) -> bool:
        """Check if MIN_DAYS_DATA of data exist in the DB."""
        try:
            from persistence.postgres import get_conn
            conn = get_conn()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT MIN(timestamp) FROM env_readings
                """)
                oldest = cur.fetchone()[0]
            if oldest is None:
                return False
            return (datetime.utcnow() - oldest.replace(tzinfo=None)).days >= MIN_DAYS_DATA
        except Exception:
            return False
