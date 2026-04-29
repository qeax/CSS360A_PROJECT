from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI(title="CSS360 Car Flip Analyzer")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve the main page
@app.get("/")
async def root():
    return FileResponse("static/index.html")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all for local testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mock database - 30 cars
MOCK_CARS = [
    {"id": 1, "make": "Toyota", "model": "Camry", "year": 2018, "price": 12000, "condition": "good", "resale_value": 14500},
    {"id": 2, "make": "Honda", "model": "Civic", "year": 2019, "price": 13500, "condition": "excellent", "resale_value": 15200},
    {"id": 3, "make": "Ford", "model": "F-150", "year": 2017, "price": 18000, "condition": "fair", "resale_value": 19500},
    {"id": 4, "make": "Chevrolet", "model": "Malibu", "year": 2020, "price": 15000, "condition": "good", "resale_value": 16800},
    {"id": 5, "make": "Toyota", "model": "RAV4", "year": 2016, "price": 14000, "condition": "fair", "resale_value": 15500},
    {"id": 6, "make": "Honda", "model": "Accord", "year": 2021, "price": 17500, "condition": "excellent", "resale_value": 19000},
    {"id": 7, "make": "Nissan", "model": "Altima", "year": 2018, "price": 11000, "condition": "good", "resale_value": 12800},
    {"id": 8, "make": "Ford", "model": "Mustang", "year": 2019, "price": 22000, "condition": "good", "resale_value": 24500},
    {"id": 9, "make": "Chevrolet", "model": "Silverado", "year": 2018, "price": 19500, "condition": "fair", "resale_value": 21000},
    {"id": 10, "make": "Toyota", "model": "Corolla", "year": 2020, "price": 14500, "condition": "excellent", "resale_value": 15800},
    {"id": 11, "make": "Honda", "model": "CR-V", "year": 2017, "price": 16000, "condition": "good", "resale_value": 17200},
    {"id": 12, "make": "Nissan", "model": "Rogue", "year": 2019, "price": 15500, "condition": "good", "resale_value": 16900},
    {"id": 13, "make": "Ford", "model": "Escape", "year": 2020, "price": 16500, "condition": "excellent", "resale_value": 18000},
    {"id": 14, "make": "Chevrolet", "model": "Equinox", "year": 2018, "price": 14000, "condition": "fair", "resale_value": 15200},
    {"id": 15, "make": "Toyota", "model": "Highlander", "year": 2019, "price": 21000, "condition": "good", "resale_value": 23500},
    {"id": 16, "make": "Jeep", "model": "Wrangler", "year": 2015, "price": 16000, "condition": "good", "resale_value": 19000},
    {"id": 17, "make": "Hyundai", "model": "Elantra", "year": 2016, "price": 8000, "condition": "fair", "resale_value": 9200},
    {"id": 18, "make": "Kia", "model": "Sportage", "year": 2017, "price": 12000, "condition": "good", "resale_value": 13500},
    {"id": 19, "make": "Ford", "model": "Focus", "year": 2014, "price": 5000, "condition": "poor", "resale_value": 5500},
    {"id": 20, "make": "Honda", "model": "Pilot", "year": 2018, "price": 20000, "condition": "excellent", "resale_value": 22500},
    {"id": 21, "make": "Toyota", "model": "Tacoma", "year": 2019, "price": 25000, "condition": "good", "resale_value": 28500},
    {"id": 22, "make": "Chevrolet", "model": "Trax", "year": 2019, "price": 13000, "condition": "good", "resale_value": 14500},
    {"id": 23, "make": "Nissan", "model": "Versa", "year": 2017, "price": 7000, "condition": "fair", "resale_value": 7800},
    {"id": 24, "make": "Hyundai", "model": "Tucson", "year": 2020, "price": 17000, "condition": "excellent", "resale_value": 18800},
    {"id": 25, "make": "Kia", "model": "Sorento", "year": 2018, "price": 16000, "condition": "good", "resale_value": 17500},
    {"id": 26, "make": "Ford", "model": "Explorer", "year": 2016, "price": 14500, "condition": "good", "resale_value": 16000},
    {"id": 27, "make": "Honda", "model": "Fit", "year": 2015, "price": 9000, "condition": "good", "resale_value": 10200},
    {"id": 28, "make": "Toyota", "model": "Prius", "year": 2018, "price": 13000, "condition": "excellent", "resale_value": 14800},
    {"id": 29, "make": "Chevrolet", "model": "Cruze", "year": 2016, "price": 8500, "condition": "fair", "resale_value": 9500},
    {"id": 30, "make": "Nissan", "model": "Maxima", "year": 2020, "price": 16500, "condition": "excellent", "resale_value": 18000}
]



@app.get("/cars")
async def get_cars(
    make: Optional[str] = Query(None, description="Filter by make (e.g., Toyota)"),
    model: Optional[str] = Query(None, description="Filter by model (e.g., Camry)"),
    max_price: Optional[float] = Query(None, description="Maximum purchase price"),
    min_year: Optional[int] = Query(None, description="Minimum year")
):
    """
    Get cars filtered by criteria, with profit/ROI calculated.
    Results sorted by profit (highest first).
    """
    results = []
    
    for car in MOCK_CARS:
        # Apply filters
        if make and car["make"].lower() != make.lower():
            continue
        if model and car["model"].lower() != model.lower():
            continue
        if max_price and car["price"] > max_price:
            continue
        if min_year and car["year"] < min_year:
            continue
        
        # Calculate profit & ROI
        profit = car["resale_value"] - car["price"]
        roi = (profit / car["price"]) * 100 if car["price"] > 0 else 0
        
        results.append({
            **car,
            "profit": round(profit, 2),
            "roi_percent": round(roi, 1)
        })
    
    # Sort by profit (descending)
    results.sort(key=lambda x: x["profit"], reverse=True)
    
    return results

@app.get("/health")
async def health():
    return {"status": "ok", "service": "CSS360 Backend"}
