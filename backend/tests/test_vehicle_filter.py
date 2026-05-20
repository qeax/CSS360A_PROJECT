from app.integrations.ebay.vehicle_filter import is_likely_vehicle_listing


def test_rejects_fashion_listing():
    assert not is_likely_vehicle_listing(
        {
            "title": "[Used] [Unused] Balenciaga Cotton Nylon Polyurethane",
            "price": 92.02,
            "brand": "Balenciaga",
            "model": "Bag",
        }
    )


def test_accepts_vehicle_with_mileage():
    assert is_likely_vehicle_listing(
        {
            "title": "2019 Toyota Camry SE",
            "price": 18500,
            "brand": "Toyota",
            "model": "Camry",
            "mileage": 42150,
        }
    )
