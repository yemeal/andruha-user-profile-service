from app.entrypoints.http.routers.health import router as health_router
from app.entrypoints.http.routers.profiles import router as profiles_router
from app.entrypoints.http.routers.settings import router as settings_router

__all__ = ["health_router", "internal_router", "profiles_router", "settings_router"]
