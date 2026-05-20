from app.services.flip import calculate_flip_score, estimate_flip_economics


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


def test_repair_rises_with_age_mileage_and_worse_condition():
    low = estimate_flip_economics(
        20_000,
        year=2022,
        mileage=25_000,
        condition="New",
        vehicle_title="Clean",
        listing_id="low",
    )
    high = estimate_flip_economics(
        20_000,
        year=2010,
        mileage=180_000,
        condition="Used",
        vehicle_title="Clean",
        listing_id="high",
    )
    salvage = estimate_flip_economics(
        20_000,
        year=2012,
        mileage=120_000,
        condition="Salvage",
        vehicle_title="Salvage",
        listing_id="salv",
    )
    assert high["repair_cost"] > low["repair_cost"]
    assert salvage["repair_cost"] > high["repair_cost"]


def test_missing_fields_use_neutral_repair_not_extreme():
    sparse = estimate_flip_economics(18_000, listing_id="sparse")
    with_year = estimate_flip_economics(18_000, year=2015, listing_id="y")
    assert 200 <= sparse["repair_cost"] <= 18_000 * 0.25
    assert sparse["repair_cost"] != with_year["repair_cost"]


def test_year_from_title_when_year_omitted():
    from_title = estimate_flip_economics(
        15_000,
        title_text="2019 Honda Civic LX",
        listing_id="t",
    )
    explicit = estimate_flip_economics(15_000, year=2019, listing_id="t2")
    assert abs(from_title["repair_cost"] - explicit["repair_cost"]) < 800


def test_unknown_condition_and_title_do_not_force_salvage_repair():
    a = estimate_flip_economics(
        20_000,
        year=2018,
        mileage=70_000,
        condition=None,
        vehicle_title=None,
        listing_id="u1",
    )
    b = estimate_flip_economics(
        20_000,
        year=2018,
        mileage=70_000,
        condition="Salvage",
        vehicle_title="Salvage",
        listing_id="u2",
    )
    assert b["repair_cost"] > a["repair_cost"] * 1.15


def test_same_listing_id_is_stable():
    a = estimate_flip_economics(15_000, year=2018, mileage=72_000, listing_id="stable-1")
    b = estimate_flip_economics(15_000, year=2018, mileage=72_000, listing_id="stable-1")
    assert a == b


def test_roi_not_flat_four_percent():
    rois = []
    for year, mi, cond in (
        (2021, 30_000, "Used"),
        (2011, 150_000, "Used"),
        (2014, 90_000, "Salvage"),
    ):
        e = estimate_flip_economics(
            20_000, year=year, mileage=mi, condition=cond, listing_id=str(year)
        )
        rois.append(calculate_flip_score(20_000, e["resale_value"], e["repair_cost"])["roi"])
    assert len({round(r, 1) for r in rois}) >= 2
