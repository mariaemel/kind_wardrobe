from fastapi import APIRouter

from app.modules.accounts.router import router as auth_router
from app.modules.system.router import router as system_router

api_router = APIRouter()
api_router.include_router(system_router)
api_router.include_router(auth_router)
