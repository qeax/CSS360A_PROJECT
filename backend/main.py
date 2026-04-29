from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List

app = FastAPI(title="CSS360 Car Flip Analyzer")

# Configure CORS for cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def calculate_flip_score(purchase_price: float, resale_value: float, repair_cost: float = 0) -> dict:
    """
    Calculates net profit and ROI percentage.
    """
    net_profit = resale_value - purchase_price - repair_cost
    roi = (net_profit / purchase_price) * 100 if purchase_price > 0 else 0
    return {
        "net_profit": round(net_profit, 2),
        "roi": round(roi, 1),
        "is_profitable": net_profit > 0
    }

# Extended mock database (30 items)[cite: 3]
# Complete list of 30 cars for the backend database
MOCK_CARS = [
    {"id": 1, "brand": "Toyota", "model": "Camry", "year": 2018, "price": 12000, "repair_cost": 800, "resale_value": 14500},
    {"id": 2, "brand": "Honda", "model": "Civic", "year": 2019, "price": 13500, "repair_cost": 500, "resale_value": 15200},
    {"id": 3, "brand": "Ford", "model": "F-150", "year": 2017, "price": 18000, "repair_cost": 1500, "resale_value": 21500},
    {"id": 4, "brand": "Chevrolet", "model": "Malibu", "year": 2016, "price": 8500, "repair_cost": 1200, "resale_value": 11000},
    {"id": 5, "brand": "Nissan", "model": "Altima", "year": 2015, "price": 7000, "repair_cost": 2000, "resale_value": 9500},
    {"id": 6, "brand": "BMW", "model": "3 Series", "year": 2014, "price": 11000, "repair_cost": 3500, "resale_value": 16000},
    {"id": 7, "brand": "Mercedes-Benz", "model": "C-Class", "year": 2018, "price": 22000, "repair_cost": 1000, "resale_value": 26500},
    {"id": 8, "brand": "Audi", "model": "A4", "year": 2017, "price": 15500, "repair_cost": 1800, "resale_value": 19000},
    {"id": 9, "brand": "Hyundai", "model": "Elantra", "year": 2020, "price": 14000, "repair_cost": 300, "resale_value": 16500},
    {"id": 10, "brand": "Kia", "model": "Optima", "year": 2019, "price": 12500, "repair_cost": 600, "resale_value": 14800},
    {"id": 11, "brand": "Subaru", "model": "Impreza", "year": 2016, "price": 9800, "repair_cost": 1100, "resale_value": 12500},
    {"id": 12, "brand": "Volkswagen", "model": "Jetta", "year": 2015, "price": 6500, "repair_cost": 1400, "resale_value": 9000},
    {"id": 13, "brand": "Mazda", "model": "CX-5", "year": 2018, "price": 17500, "repair_cost": 800, "resale_value": 20500},
    {"id": 14, "brand": "Lexus", "model": "RX 350", "year": 2014, "price": 14000, "repair_cost": 2500, "resale_value": 19500},
    {"id": 15, "brand": "Jeep", "model": "Grand Cherokee", "year": 2017, "price": 19000, "repair_cost": 3000, "resale_value": 24000},
    {"id": 16, "brand": "Tesla", "model": "Model 3", "year": 2021, "price": 28000, "repair_cost": 500, "resale_value": 32000},
    {"id": 17, "brand": "Volvo", "model": "S60", "year": 2015, "price": 8000, "repair_cost": 1800, "resale_value": 11500},
    {"id": 18, "brand": "Porsche", "model": "Macan", "year": 2016, "price": 25000, "repair_cost": 4500, "resale_value": 34000},
    {"id": 19, "brand": "GMC", "model": "Sierra", "year": 2018, "price": 23000, "repair_cost": 1200, "resale_value": 27000},
    {"id": 20, "brand": "Dodge", "model": "Charger", "year": 2019, "price": 16000, "repair_cost": 2200, "resale_value": 20500},
    {"id": 21, "brand": "Ram", "model": "1500", "year": 2017, "price": 20000, "repair_cost": 1800, "resale_value": 25000},
    {"id": 22, "brand": "Land Rover", "model": "Discovery", "year": 2016, "price": 18000, "repair_cost": 5500, "resale_value": 24000},
    {"id": 23, "brand": "Jaguar", "model": "XF", "year": 2015, "price": 12000, "repair_cost": 4000, "resale_value": 17500},
    {"id": 24, "brand": "Mini", "model": "Cooper", "year": 2014, "price": 5500, "repair_cost": 2100, "resale_value": 9000},
    {"id": 25, "brand": "Buick", "model": "Enclave", "year": 2018, "price": 16500, "repair_cost": 900, "resale_value": 19500},
    {"id": 26, "brand": "Cadillac", "model": "CTS", "year": 2016, "price": 14500, "repair_cost": 3200, "resale_value": 19000},
    {"id": 27, "brand": "Infiniti", "model": "Q50", "year": 2017, "price": 15000, "repair_cost": 1500, "resale_value": 18500},
    {"id": 28, "brand": "Acura", "model": "TLX", "year": 2019, "price": 21000, "repair_cost": 400, "resale_value": 24500},
    {"id": 29, "brand": "Mitsubishi", "model": "Outlander", "year": 2015, "price": 6000, "repair_cost": 1300, "resale_value": 8500},
    {"id": 30, "brand": "Nissan", "model": "Maxima", "year": 2020, "price": 16500, "repair_cost": 400, "resale_value": 18500}
]

@app.get("/cars")
async def get_cars(
    brand: Optional[str] = Query(None),
    max_price: Optional[float] = Query(None),
    min_year: Optional[int] = Query(None)
):
    """
    Enhanced search logic to support the marketplace search button.
    """
    results = []
    for car in MOCK_CARS:
        # Partial string match for brand search
        if brand and brand.lower() not in car["brand"].lower():
            continue
        if max_price and car["price"] > max_price:
            continue
        if min_year and car["year"] < min_year:
            continue
            
        analysis = calculate_flip_score(car["price"], car["resale_value"], car.get("repair_cost", 0))
        results.append({**car, **analysis})
    
    # Sort by ROI descending to show best deals first
    return sorted(results, key=lambda x: x["roi"], reverse=True)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "CSS360 Backend"}