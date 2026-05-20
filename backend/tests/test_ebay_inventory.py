from app.integrations.ebay.inventory import ebay_listing_dict_to_car_view
from app.integrations.ebay.parse_item import merge_search_summary, parse_get_item


def test_parse_get_item_extracts_vehicle_facets():
    item = {
        "itemId": "v1|99|0",
        "title": "2019 Toyota Camry SE",
        "itemWebUrl": "https://www.ebay.com/itm/99",
        "price": {"value": "18500", "currency": "USD"},
        "condition": "Used",
        "buyingOptions": ["FIXED_PRICE"],
        "bidCount": 0,
        "localizedAspects": [
            {"localizedAspectName": "Make", "localizedAspectValues": ["Toyota"]},
            {"localizedAspectName": "Model", "localizedAspectValues": ["Camry"]},
            {"localizedAspectName": "Year", "localizedAspectValues": ["2019"]},
            {"localizedAspectName": "Mileage", "localizedAspectValues": ["42,150 mi"]},
            {"localizedAspectName": "Drive Type", "localizedAspectValues": ["FWD"]},
            {"localizedAspectName": "Body Style", "localizedAspectValues": ["Sedan"]},
            {"localizedAspectName": "Title", "localizedAspectValues": ["Clean"]},
        ],
        "itemLocation": {
            "address": {"city": "Seattle", "stateOrProvince": "WA", "country": "US"},
            "postalCode": "98101",
        },
        "estimatedAvailabilities": [
            {"deliveryOptions": ["SHIP_TO_HOME", "SELLER_ARRANGED_LOCAL_PICKUP"]}
        ],
        "image": {"imageUrl": "https://i.ebayimg.com/a.jpg"},
        "additionalImages": [{"imageUrl": "https://i.ebayimg.com/b.jpg"}],
        "seller": {"username": "dealer_test"},
        "shortDescription": "Well maintained Camry.",
    }
    parsed = parse_get_item(item)
    assert parsed["brand"] == "Toyota"
    assert parsed["model"] == "Camry"
    assert parsed["year"] == 2019
    assert parsed["mileage"] == 42150
    assert parsed["vehicle_title"] == "Clean"
    assert parsed["listing_format"] == "BUY_IT_NOW"
    assert parsed["seller_username"] == "dealer_test"
    assert len(parsed["image_urls"]) == 2
    assert parsed["delivery"]["ship_to_home"] is True
    assert parsed["delivery"]["local_pickup"] is True


def test_merge_search_summary_prefers_get_item():
    search = {
        "external_listing_id": "v1|1|0",
        "title": "2018 Honda Civic",
        "price": "17000",
        "location_city": "Portland",
        "source": "ebay",
    }
    detail = {
        "itemId": "v1|1|0",
        "title": "2018 Honda Civic LX",
        "localizedAspects": [
            {"localizedAspectName": "Make", "localizedAspectValues": ["Honda"]},
            {"localizedAspectName": "Model", "localizedAspectValues": ["Civic"]},
            {"localizedAspectName": "Year", "localizedAspectValues": ["2018"]},
        ],
        "price": {"value": "16950", "currency": "USD"},
    }
    merged = merge_search_summary(search, detail)
    assert merged["brand"] == "Honda"
    assert merged["model"] == "Civic"
    assert float(merged["price"]) == 16950.0


def test_ebay_listing_dict_to_car_view_parses_title():
    item = {
        "external_listing_id": "v1|123|0",
        "title": "2019 Toyota Camry SE Sedan 4-Door",
        "price": 18500,
        "currency": "USD",
        "condition": "Used",
        "location": {"city": "Seattle", "region": "WA", "country": "United States"},
        "mileage": 42150,
        "vehicle_title": "Clean",
        "listing_format": "BUY_IT_NOW",
        "listing_url": "https://www.ebay.com/itm/123",
        "image_urls": ["https://i.ebayimg.com/sample.jpg"],
        "aspects_json": [
            {"localizedAspectName": "Drive Type", "localizedAspectValues": ["FWD"]},
            {"localizedAspectName": "Body Style", "localizedAspectValues": ["Sedan"]},
        ],
        "delivery": {"ship_to_home": True, "local_pickup": True, "in_store_pickup": False},
        "seller_username": "dealer1",
        "source": "ebay",
    }
    view = ebay_listing_dict_to_car_view(item, 1)
    assert view is not None
    assert view.brand == "Toyota"
    assert "Camry" in view.model
    assert view.year == 2019
    assert view.mileage == 42150
    assert view.vehicle_title == "Clean"
    assert view.external_seller.username == "dealer1"


def test_ebay_listing_dict_skips_error_rows():
    assert ebay_listing_dict_to_car_view({"error": "fail"}, 1) is None
