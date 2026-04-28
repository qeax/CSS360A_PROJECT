from fastapi import FastAPI

app = FastAPI()

@app.get("/api/cars")
async def get_cars():
    # temporary fake car list
    return [
        {"id": 1, "brand": "BMW", "model": "M3", "price": 45000},
        {"id": 2, "brand": "Audi", "model": "RS6", "price": 85000},
        {"id": 3, "brand": "Mercedes", "model": "C63", "price": 60000}
    ]