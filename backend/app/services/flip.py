def calculate_flip_score(
    purchase_price: float, resale_value: float, repair_cost: float = 0
) -> dict:
    net_profit = resale_value - purchase_price - repair_cost
    roi = (net_profit / purchase_price) * 100 if purchase_price > 0 else 0
    return {
        "net_profit": round(net_profit, 2),
        "roi": round(roi, 1),
        "is_profitable": net_profit > 0,
    }
