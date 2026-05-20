from app.services.flip import calculate_flip_score, estimate_flip_from_listing


def test_positive_profit_and_roi():
    out = calculate_flip_score(10_000, 12_500, 500)
    assert out["net_profit"] == 2000.0
    assert out["roi"] == 20.0
    assert out["is_profitable"] is True


def test_zero_purchase_price_roi_is_zero():
    out = calculate_flip_score(0, 5_000, 0)
    assert out["roi"] == 0
    assert out["net_profit"] == 5000.0


def test_unprofitable():
    out = calculate_flip_score(10_000, 9_000, 500)
    assert out["is_profitable"] is False
    assert out["net_profit"] == -1500.0


def test_fixed_eight_twelve_formula_is_four_percent():
    price = 20_000.0
    repair = round(price * 0.08, 2)
    resale = round(price * 1.12, 2)
    assert calculate_flip_score(price, resale, repair)["roi"] == 4.0


def test_heuristic_varies_by_vehicle_factors():
    low_mi_clean = estimate_flip_from_listing(
        20_000,
        year=2022,
        mileage=25_000,
        condition="Used",
        vehicle_title="Clean",
    )
    high_mi_salvage = estimate_flip_from_listing(
        20_000,
        year=2010,
        mileage=165_000,
        condition="Used",
        vehicle_title="Salvage",
    )
    roi_clean = calculate_flip_score(20_000, low_mi_clean[1], low_mi_clean[0])["roi"]
    roi_salvage = calculate_flip_score(20_000, high_mi_salvage[1], high_mi_salvage[0])["roi"]
    assert roi_clean != roi_salvage
    assert roi_salvage < roi_clean


def test_heuristic_not_always_four_percent():
    repair, resale = estimate_flip_from_listing(
        15_000, year=2018, mileage=72_000, vehicle_title="Clean"
    )
    assert calculate_flip_score(15_000, resale, repair)["roi"] != 4.0
