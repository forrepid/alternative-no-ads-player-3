import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import resolve
from app.api.routes import router
from app.api.system import router as system_router
from app.core.config import settings
from app.core.http import http
from app.main_version import APP_VERSION

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await http.close()


app = FastAPI(title="StreamBridge", version=APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",")
                   if origin.strip()],
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["Accept", "Content-Type"],
)

@app.middleware("http")
async def private_network_access(request: Request, call_next):
    allowed_origins = {origin.strip() for origin in settings.cors_origins.split(",")
                       if origin.strip()}
    # Chrome PNA preflight (OPTIONS) isteklerini karsila
    if request.method == "OPTIONS" and request.headers.get("Access-Control-Request-Private-Network"):
        from fastapi.responses import Response
        origin = request.headers.get("Origin", "")
        if origin not in allowed_origins:
            return Response(status_code=403)
        return Response(status_code=200, headers={
            "Access-Control-Allow-Private-Network": "true",
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Accept, Content-Type",
        })
    response = await call_next(request)
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response
    
app.include_router(router)
app.include_router(system_router)
app.include_router(resolve.router)

STATIC_DIR = os.path.join(PROJECT_ROOT, "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port)
