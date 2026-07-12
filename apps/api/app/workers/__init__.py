"""AroTrade Celery application and task registry.

Workers configured:
  - scanner_tasks  : Run scanner pipeline on new closed candles
  - reconcile_tasks: Reconcile broker positions with local trades
  - notify_tasks   : Fire notifications for expiring/triggered signals

Beat schedule:
  - Every 60s (configurable): scan all active profiles
  - Every 5m: reconcile open trades with broker positions
  - Every 5m: expire stale approved signals

Run the worker:
  celery -A app.workers:celery_app worker -l info
Run beat:
  celery -A app.workers:celery_app beat -l info
"""

from celery import Celery
from app.config import settings

celery_app = Celery(
    "arotrade",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)

# Autodiscover tasks
celery_app.autodiscover_tasks([
    "app.workers.scanner_tasks",
    "app.workers.reconcile_tasks",
    "app.workers.notify_tasks",
])

# Beat schedule
scanner_interval = settings.SCANNER_DEFAULT_INTERVAL_SECONDS

celery_app.conf.beat_schedule = {
    "scanner-periodic": {
        "task": "app.workers.scanner_tasks.run_all_scanner_profiles",
        "schedule": scanner_interval,
    },
    "reconcile-open-positions": {
        "task": "app.workers.reconcile_tasks.reconcile_broker_positions",
        "schedule": 300,  # every 5 minutes
    },
    "expire-stale-signals": {
        "task": "app.workers.notify_tasks.expire_stale_signals",
        "schedule": 300,  # every 5 minutes
    },
    "notify-entry-zone-alerts": {
        "task": "app.workers.notify_tasks.check_entry_zones",
        "schedule": settings.SCANNER_DEFAULT_INTERVAL_SECONDS,
    },
}
