from fastapi import APIRouter

from services.oa_admin.apps.external.feishu.api.router import router as feishu_router

router = APIRouter()
router.include_router(feishu_router)
