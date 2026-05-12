from app.services.flip import calculate_flip_score


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
