from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import os

# Database configuration
APP_ENV = os.getenv("APP_ENV", "development").lower()


def build_database_url() -> str:
    explicit_url = os.getenv("DATABASE_URL")
    if explicit_url:
        return explicit_url

    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT", "3306")
    db_name = os.getenv("DB_NAME")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")

    has_discrete_db_config = all([db_host, db_name, db_user, db_password])
    if has_discrete_db_config:
        return f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

    if APP_ENV in ("development", "dev", "local"):
        # Local-safe fallback for development only.
        return "sqlite:///./cars_dev.db"

    raise RuntimeError("Missing database configuration. Provide DATABASE_URL or DB_* variables.")


DATABASE_URL = build_database_url()

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Car model for database
class Car(Base):
    __tablename__ = "cars"
    
    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String(100))
    model = Column(String(100))
    year = Column(Integer)
    price = Column(Float)
    repair_cost = Column(Float, default=0)
    resale_value = Column(Float)
    mileage = Column(Integer, nullable=True)
    condition = Column(String(50), nullable=True)
    
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
    {"id": 11, "brand": "Subaru", "model": "Impreza", "year": 2016, "price": 13000, "repair_cost": 1100, "resale_value": 12500},
    {"id": 12, "brand": "Volkswagen", "model": "Jetta", "year": 2015, "price": 6500, "repair_cost": 1400, "resale_value": 9000},
    {"id": 13, "brand": "Mazda", "model": "CX-5", "year": 2018, "price": 17500, "repair_cost": 800, "resale_value": 20500},
    {"id": 14, "brand": "Lexus", "model": "RX 350", "year": 2014, "price": 14000, "repair_cost": 2500, "resale_value": 19500},
    {"id": 15, "brand": "Jeep", "model": "Grand Cherokee", "year": 2017, "price": 19000, "repair_cost": 3000, "resale_value": 24000},
    {"id": 16, "brand": "Tesla", "model": "Model 3", "year": 2021, "price": 28000, "repair_cost": 500, "resale_value": 32000},
    {"id": 17, "brand": "Volvo", "model": "S60", "year": 2015, "price": 8000, "repair_cost": 1800, "resale_value": 11500},
    {"id": 18, "brand": "Porsche", "model": "Macan", "year": 2016, "price": 25000, "repair_cost": 4500, "resale_value": 34000},
    {"id": 19, "brand": "GMC", "model": "Sierra", "year": 2018, "price": 23000, "repair_cost": 1200, "resale_value": 27000},
    {"id": 20, "brand": "Dodge", "model": "Charger", "year": 2019, "price": 25000, "repair_cost": 2200, "resale_value": 20500},
    {"id": 21, "brand": "Ram", "model": "1500", "year": 2017, "price": 24950, "repair_cost": 1800, "resale_value": 25000},
    {"id": 22, "brand": "Land Rover", "model": "Discovery", "year": 2016, "price": 18000, "repair_cost": 5500, "resale_value": 24000},
    {"id": 23, "brand": "Jaguar", "model": "XF", "year": 2015, "price": 12000, "repair_cost": 4000, "resale_value": 17500},
    {"id": 24, "brand": "Mini", "model": "Cooper", "year": 2014, "price": 5500, "repair_cost": 2100, "resale_value": 9000},
    {"id": 25, "brand": "Buick", "model": "Enclave", "year": 2018, "price": 16500, "repair_cost": 900, "resale_value": 19500},
    {"id": 26, "brand": "Cadillac", "model": "CTS", "year": 2016, "price": 14500, "repair_cost": 3200, "resale_value": 19000},
    {"id": 27, "brand": "Infiniti", "model": "Q50", "year": 2017, "price": 15000, "repair_cost": 1500, "resale_value": 18500},
    {"id": 28, "brand": "Acura", "model": "TLX", "year": 2019, "price": 21000, "repair_cost": 400, "resale_value": 24500},
    {"id": 29, "brand": "Mitsubishi", "model": "Outlander", "year": 2015, "price": 8900, "repair_cost": 1300, "resale_value": 8500},
    {"id": 30, "brand": "Nissan", "model": "Maxima", "year": 2020, "price": 16500, "repair_cost": 400, "resale_value": 18500}
]

for car in MOCK_CARS:
    car.setdefault("condition", None)

# Database initialization
def init_db():
    """Create tables and populate with mock data if empty"""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Check if database is empty
        if db.query(Car).count() == 0:
            # Populate with mock data
            for car_data in MOCK_CARS:
                car_data.setdefault("condition", None)
                car = Car(**car_data)
                db.add(car)
            db.commit()
            print("Database initialized with mock data")
    finally:
        db.close()

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Initialize database on startup
try:
    init_db()
    USE_DATABASE = True
    print("Connected to database")
except Exception as e:
    USE_DATABASE = False
    print(f"Database connection failed: {e}")
    if APP_ENV in ("development", "dev", "local"):
        print("Using in-memory mock data")
    else:
        print("Running in degraded mode without database")


@app.get("/cars")
async def get_cars(
    make: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    min_year: Optional[int] = Query(None),
    max_year: Optional[int] = Query(None),
    condition: Optional[str] = Query(None),
    max_price: Optional[float] = Query(None),
    min_profit: Optional[float] = Query(None),
    min_roi: Optional[float] = Query(None),
    sort_by: Optional[str] = Query(None),  # roi, net_profit, price
    sort_order: Optional[str] = Query("desc")  # asc, desc
):
    results = []
    for car in MOCK_CARS:
        # --- 1. Basic Filters ---
        if make and make.lower() not in car["brand"].lower(): continue
        if model and model.lower() not in car["model"].lower(): continue
        if min_year and car["year"] < min_year: continue
        if max_year and car["year"] > max_year: continue
        condition_value = car.get("condition")
        if condition and (
            not condition_value or condition.lower() not in condition_value.lower()
        ):
            continue
        if max_price and car["price"] > max_price: continue
            
        # --- 2. Calculate Profit/ROI ---
        analysis = calculate_flip_score(car["price"], car["resale_value"], car.get("repair_cost", 0))
        
        # --- 3. Profit/ROI Filters (Must happen AFTER calculation) ---
        if min_profit and analysis["net_profit"] < min_profit: continue
        if min_roi and analysis["roi"] < min_roi: continue
            
        car_data = {**car, **analysis}
        if "mileage" not in car_data:
            car_data["mileage"] = 75000 + (car["id"] * 1500) 
        if "condition" not in car_data:
            car_data["condition"] = None
            
        results.append(car_data)
    
    if sort_by:
        reverse_sort = True if sort_order == "desc" else False
        if sort_by == "net_profit":
            results.sort(key=lambda x: x["net_profit"], reverse=reverse_sort)
        elif sort_by == "price":
            results.sort(key=lambda x: x["price"], reverse=reverse_sort)
        elif sort_by == "roi":
            results.sort(key=lambda x: x["roi"], reverse=reverse_sort)

    return results

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "CSS360 Backend",
        "database_connected": USE_DATABASE
    }