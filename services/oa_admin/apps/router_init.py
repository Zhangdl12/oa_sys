from fastapi import APIRouter

from services.oa_admin.apps.auth.api.router import router as auth_router
from services.oa_admin.apps.external.api.router import router as external_router
from services.oa_admin.apps.health.api.router import router as health_router
from services.oa_admin.apps.operation_log.api.router import router as operation_log_router
from services.oa_admin.apps.permission.api.router import router as permission_router
from services.oa_admin.apps.role.api.router import router as role_router
from services.oa_admin.apps.schedule.api.router import router as schedule_router
from services.oa_admin.apps.user.api.router import router as user_router
from services.oa_admin.core.config import get_settings

settings = get_settings()
api_router = APIRouter(prefix=settings.api_prefix)
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(permission_router, prefix="/permissions", tags=["permissions"])
api_router.include_router(role_router, prefix="/roles", tags=["roles"])
api_router.include_router(user_router, prefix="/users", tags=["users"])
api_router.include_router(operation_log_router, prefix="/operation-logs", tags=["operation-logs"])
api_router.include_router(external_router, prefix="/external", tags=["external"])
api_router.include_router(schedule_router, prefix="/schedule", tags=["schedule"])
