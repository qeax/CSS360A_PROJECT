

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://css360.qeax.cloud"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/cars")
async def get_cars():
    # temporary fake car list
    return [
        {"id": 1, "brand": "BMW", "model": "M3", "price": 45000},
        {"id": 2, "brand": "Audi", "model": "RS6", "price": 85000},
        {"id": 3, "brand": "Mercedes", "model": "C63", "price": 60000}
    ]
    
@app.get("/health")
async def health():
    return {"status": "ok"}