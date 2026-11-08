from celery import Celery
from celery.schedules import crontab
from backend.app.core.config import settings

celery_app = Celery(
    "inventory_tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["backend.app.tasks.periodic_tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    worker_prefetch_multiplier=1,
    beat_schedule={
        # 1. Hourly: Autonomous ROP Replenishment Engine Sweep
        "evaluate-reorder-points-hourly": {
            "task": "backend.app.tasks.periodic_tasks.evaluate_reorder_points",
            "schedule": crontab(minute=0),
        },
        # 2. Daily 02:00: Refresh ML Demand Forecasts
        "refresh-demand-forecasts-daily": {
            "task": "backend.app.tasks.periodic_tasks.refresh_demand_forecasts",
            "schedule": crontab(hour=2, minute=0),
        },
        # 3. 6-Hourly: Follow-up Delayed & Unconfirmed Purchase Orders
        "followup-delayed-pos-6hourly": {
            "task": "backend.app.tasks.periodic_tasks.followup_delayed_pos",
            "schedule": crontab(minute=30, hour="*/6"),
        },
        # 4. Daily 04:00: Stock Drift Integrity Audit
        "audit-inventory-drift-daily": {
            "task": "backend.app.tasks.periodic_tasks.audit_inventory_drift",
            "schedule": crontab(hour=4, minute=0),
        },
        # 5. Weekly (Sundays 03:00): Dead Stock Scanner
        "detect-dead-stock-weekly": {
            "task": "backend.app.tasks.periodic_tasks.detect_dead_stock",
            "schedule": crontab(hour=3, minute=0, day_of_week="sunday"),
        },
        # 6. Daily 05:00: Full Anomaly Sweep
        "run-full-anomaly-sweep-daily": {
            "task": "backend.app.tasks.periodic_tasks.run_full_anomaly_sweep",
            "schedule": crontab(hour=5, minute=0),
        },
    }
)

