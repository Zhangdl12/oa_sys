import asyncio
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from services.oa_admin.apps.external.feishu.models.feishu import FeishuCardNotifyRequest
from services.oa_admin.core.config import Settings
from services.oa_admin.worker.celery_app import celery_app
from services.oa_admin.worker.tasks.feishu_tasks import (
    TASK_NAME,
    send_hourly_feishu_card_notify_async,
)


def run_async(coro):
    return asyncio.run(coro)


class StubFeishuManagement:
    def __init__(self) -> None:
        self.card_payloads: list[FeishuCardNotifyRequest] = []
        self.sender_user_ids: list[int | None] = []
        self.request_ids: list[str] = []

    async def send_card_notify(
        self,
        payload: FeishuCardNotifyRequest,
        sender_user_id: int | None = None,
        request_id: str = "",
    ) -> dict[str, Any]:
        self.card_payloads.append(payload)
        self.sender_user_ids.append(sender_user_id)
        self.request_ids.append(request_id)
        return {"data": {"message_id": "om_hourly"}}


def test_hourly_feishu_task_skips_when_disabled() -> None:
    manager = StubFeishuManagement()

    result = run_async(
        send_hourly_feishu_card_notify_async(
            settings=Settings(
                feishu_hourly_notify_enabled=False,
                feishu_hourly_notify_user_id="user_xxx",
            ),
            feishu_management=manager,
        )
    )

    assert result == {"status": "skipped", "reason": "disabled"}
    assert manager.card_payloads == []


def test_hourly_feishu_task_skips_when_user_id_missing() -> None:
    manager = StubFeishuManagement()

    result = run_async(
        send_hourly_feishu_card_notify_async(
            settings=Settings(
                feishu_hourly_notify_enabled=True,
                feishu_hourly_notify_user_id="",
            ),
            feishu_management=manager,
        )
    )

    assert result == {"status": "skipped", "reason": "missing_user_id"}
    assert manager.card_payloads == []


def test_hourly_feishu_task_sends_user_id_card() -> None:
    manager = StubFeishuManagement()
    now = datetime(2026, 6, 24, 10, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    result = run_async(
        send_hourly_feishu_card_notify_async(
            settings=Settings(
                feishu_hourly_notify_enabled=True,
                feishu_hourly_notify_user_id="user_xxx",
            ),
            feishu_management=manager,
            now=now,
        )
    )

    assert result["status"] == "sent"
    assert result["request_id"] == "celery-hourly-feishu-2026062410"
    assert manager.sender_user_ids == [None]
    assert manager.request_ids == ["celery-hourly-feishu-2026062410"]
    payload = manager.card_payloads[0]
    assert payload.receive_id_type == "user_id"
    assert payload.receive_id == "user_xxx"
    assert payload.content_summary == "OA 每小时定时通知 2026-06-24 10:00"
    assert payload.card["header"]["title"]["content"] == "OA 每小时定时通知"
    detail = payload.card["body"]["elements"][0]["content"]
    assert "时间：2026-06-24 10:00:00" in detail
    assert "来源：Celery Beat" in detail


def test_celery_app_registers_hourly_feishu_task() -> None:
    assert TASK_NAME in celery_app.tasks


def test_hourly_feishu_task_sends_again_in_same_hour() -> None:
    manager = StubFeishuManagement()
    now = datetime(2026, 6, 24, 10, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    settings = Settings(
        feishu_hourly_notify_enabled=True,
        feishu_hourly_notify_user_id="user_xxx",
    )

    first = run_async(
        send_hourly_feishu_card_notify_async(
            settings=settings,
            feishu_management=manager,
            now=now,
        )
    )
    second = run_async(
        send_hourly_feishu_card_notify_async(
            settings=settings,
            feishu_management=manager,
            now=now,
        )
    )

    assert first["status"] == "sent"
    assert second["status"] == "sent"
    assert len(manager.card_payloads) == 2
    assert manager.request_ids == [
        "celery-hourly-feishu-2026062410",
        "celery-hourly-feishu-2026062410",
    ]


def test_celery_beat_schedules_hourly_feishu_task() -> None:
    entry = celery_app.conf.beat_schedule["send-hourly-feishu-card-notify"]

    assert entry["task"] == TASK_NAME
    assert entry["schedule"].__class__.__name__ == "crontab"
    assert getattr(entry["schedule"], "_orig_minute", None) == 0
