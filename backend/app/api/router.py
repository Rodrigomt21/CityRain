from fastapi import APIRouter

from app.api.v1 import captures, media, stats

router = APIRouter(prefix="/api/v1")
router.include_router(captures.router, prefix="/captures", tags=["captures — Dashboard"])
router.include_router(media.router, tags=["ingest — Jetson"])
router.include_router(stats.router, prefix="/stats", tags=["stats — Dashboard"])
