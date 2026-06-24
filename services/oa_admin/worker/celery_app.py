from celery import Celery
from celery.schedules import crontab
from datetime import timedelta

from services.oa_admin.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "oa_admin",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["services.oa_admin.worker.tasks.feishu_tasks"],
)

celery_app.conf.update(
    timezone="Asia/Shanghai",
    enable_utc=False,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)

celery_app.conf.beat_schedule = {
    "send-hourly-feishu-card-notify": {
        "task": "send_hourly_feishu_card_notify",
        "schedule": crontab(minute=0),
        # "schedule":timedelta(seconds=5)
    }
}
