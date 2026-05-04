from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import cars, health

app = FastAPI(title="CSS360 Car Flip Analyzer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Expose both /cars and /api/cars (and health) so Traefik works with or without StripPrefix on `/api`.
app.include_router(cars.router)
app.include_router(cars.router, prefix="/api")
app.include_router(health.router)
app.include_router(health.router, prefix="/api")
