from fastapi.testclient import TestClient

from services.oa_admin.apps.schedule.api import router as schedule_router
from services.oa_admin.core.config import Settings, get_settings
from services.oa_admin.main import app
from services.oa_admin.worker.tasks.feishu_tasks import TASK_NAME


class StubAsyncResult:
    id = "celery-task-id"


def override_settings() -> Settings:
    return Settings(schedule_trigger_token="schedule-token")


def test_schedule_trigger_queues_hourly_feishu_task(monkeypatch) -> None:
    captured: dict[str, bool] = {}

    def fake_apply_async() -> StubAsyncResult:
        captured["called"] = True
        return StubAsyncResult()

    monkeypatch.setattr(
        schedule_router.send_hourly_feishu_card_notify,
        "apply_async",
        fake_apply_async,
    )
    app.dependency_overrides[get_settings] = override_settings
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/schedule/feishu-hourly-notify/trigger",
                headers={"X-Schedule-Trigger-Token": "schedule-token"},
                json={},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["data"] == {
        "status": "queued",
        "task_name": TASK_NAME,
        "task_id": "celery-task-id",
    }
    assert captured == {"called": True}


def test_schedule_trigger_rejects_missing_token(monkeypatch) -> None:
    captured: dict[str, bool] = {}

    def fake_apply_async() -> StubAsyncResult:
        captured["called"] = True
        return StubAsyncResult()

    monkeypatch.setattr(
        schedule_router.send_hourly_feishu_card_notify,
        "apply_async",
        fake_apply_async,
    )
    app.dependency_overrides[get_settings] = override_settings
    try:
        with TestClient(app) as client:
            response = client.post("/v1/schedule/feishu-hourly-notify/trigger", json={})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 40300
    assert captured == {}


def test_schedule_trigger_rejects_bad_token(monkeypatch) -> None:
    captured: dict[str, bool] = {}

    def fake_apply_async() -> StubAsyncResult:
        captured["called"] = True
        return StubAsyncResult()

    monkeypatch.setattr(
        schedule_router.send_hourly_feishu_card_notify,
        "apply_async",
        fake_apply_async,
    )
    app.dependency_overrides[get_settings] = override_settings
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/schedule/feishu-hourly-notify/trigger",
                headers={"X-Schedule-Trigger-Token": "bad-token"},
                json={},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == 40300
    assert captured == {}
