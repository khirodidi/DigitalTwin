# ai/training/train_all.py — Master training script

import argparse, logging, sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO,format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",datefmt="%Y-%m-%d %H:%M:%S")
logger=logging.getLogger("train_all")
MODEL_DIR=Path("models"); MODEL_DIR.mkdir(exist_ok=True)

try:
    import mlflow; mlflow.set_experiment("digital_twin_ai"); MLFLOW=True
except ImportError:
    MLFLOW=False

def log_metrics(run_name,metrics):
    if not MLFLOW or not metrics: return
    with mlflow.start_run(run_name=run_name):
        for k,v in metrics.items(): mlflow.log_metric(k,v)
        mlflow.log_param("trained_at",datetime.utcnow().isoformat())

def run_fire():
    logger.info("━━━━ ④ Fire detection & localisation ━━━━")
    try:
        from ai.training.fire import train_fire_model
        m = train_fire_model(model_path=str(MODEL_DIR/"fire_convlstm.pt"))
        log_metrics("fire", m); logger.info(f"  ✓ {m}"); return m
    except Exception as e:
        logger.error(f"  ✗ {e}", exc_info=True); return {}


def run_trajectory(days=30):
    logger.info("━━━━ ⑤ Trajectory learning ━━━━")
    try:
        from ai.training.trajectory import train_trajectories
        m = train_trajectories(days=days, activate=True)
        logger.info(f"  ✓ {m.get('updated',0)} route(s) updated"); return m
    except Exception as e:
        logger.error(f"  ✗ {e}", exc_info=True); return {}


def run_movement(days=30):
    logger.info("━━━━ ① Movement optimiser ━━━━")
    try:
        from ai.training.movement import train_movement_model
        m=train_movement_model(days=days,model_path=str(MODEL_DIR/"movement_lstm.pt"))
        log_metrics("movement",m); logger.info(f"  ✓ {m}"); return m
    except Exception as e: logger.error(f"  ✗ {e}",exc_info=True); return {}

def run_evacuation(days=90):
    logger.info("━━━━ ② Smart evacuation ━━━━")
    try:
        from ai.training.evacuation import train_danger_model
        m=train_danger_model(days=days,model_path=str(MODEL_DIR/"danger_xgb.joblib"))
        log_metrics("evacuation",m); logger.info(f"  ✓ {m}"); return m
    except Exception as e: logger.error(f"  ✗ {e}",exc_info=True); return {}

def run_monitor(days=30):
    logger.info("━━━━ ③ System monitor ━━━━")
    try:
        from ai.training.monitor import train_monitor_models
        m=train_monitor_models(days=days,model_dir=str(MODEL_DIR))
        log_metrics("monitor",m); logger.info(f"  ✓ {m}"); return m
    except Exception as e: logger.error(f"  ✗ {e}",exc_info=True); return {}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--model",
        choices=["all","movement","evacuation","monitor","fire","trajectory"],
        default="all")
    parser.add_argument("--days",type=int,default=30)
    parser.add_argument("--skip-check",action="store_true")
    args=parser.parse_args()
    start=datetime.utcnow()
    logger.info(f"╔══ Digital Twin AI training | {args.model} | {start:%Y-%m-%d %H:%M} UTC ══╗")
    if not args.skip_check:
        from ai.training.drift import check_data_quality
        issues=check_data_quality()
        if issues: logger.warning(f"Quality issues: {issues}")
    all_metrics={}
    # Fire first — evacuation uses its output as an input feature
    if args.model in ("all","fire"):       all_metrics["fire"]=run_fire()
    if args.model in ("all","movement"):   all_metrics["movement"]=run_movement(args.days)
    if args.model in ("all","trajectory"): all_metrics["trajectory"]=run_trajectory(args.days)
    if args.model in ("all","evacuation"): all_metrics["evacuation"]=run_evacuation(max(args.days,90))
    if args.model in ("all","monitor"):    all_metrics["monitor"]=run_monitor(args.days)
    elapsed=(datetime.utcnow()-start).total_seconds()
    logger.info(f"╚══ Done in {elapsed:.1f}s | {all_metrics} ══╝")
    try:
        import requests
        requests.post("http://localhost:8000/api/system/reload-models",timeout=5)
        logger.info("  Engine reloaded models.")
    except Exception: pass

if __name__=="__main__": main()
