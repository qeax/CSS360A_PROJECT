import pytest
from app.services.flip import calculate_flip_score

class TestSearchParameterValidation:
    """
    Tests for input validation.
    Note: These are placeholders for when the validator service is fully implemented.
    """
    
    def test_rejects_negative_price(self):
        """Should reject negative max_price values"""
        # Placeholder for future validator implementation
        pytest.skip("Input validator service not yet implemented in backend")
    
    def test_rejects_future_year(self):
        """Should reject years in the future"""
        # Placeholder for future year validation logic
        pytest.skip("Year validation logic not yet implemented in backend")


class TestProfitCalculation:
    """Tests for flip score and ROI calculation logic from app.services.flip"""
    
    def test_calculates_positive_profit(self):
        """Should calculate positive profit when resale > purchase price + costs"""
        purchase_price = 10000
        resale_value = 12500
        repair_cost = 500
        
        # Expected Net Profit: 12500 - 10000 - 500 = 2000
        result = calculate_flip_score(purchase_price, resale_value, repair_cost)
        
        assert result["net_profit"] == 2000
        assert result["is_profitable"] is True
    
    def test_calculates_roi_percentage(self):
        """Should calculate ROI correctly as (Net Profit / Purchase Price) * 100"""
        purchase_price = 10000
        resale_value = 12000
        repair_cost = 0
        
        # Expected ROI: (2000 / 10000) * 100 = 20.0%
        result = calculate_flip_score(purchase_price, resale_value, repair_cost)
        
        assert result["roi"] == 20.0

    def test_handles_unprofitable_vehicles(self):
        """Should identify vehicles with negative or zero profit as not profitable"""
        # Scenario 1: Financial loss
        result_loss = calculate_flip_score(purchase_price=10000, resale_value=8000, repair_cost=500)
        assert result_loss["is_profitable"] is False
        assert result_loss["net_profit"] < 0
        
        # Scenario 2: Break-even (Profit is exactly 0)
        result_even = calculate_flip_score(purchase_price=10000, resale_value=10500, repair_cost=500)
        assert result_even["is_profitable"] is False
        assert result_even["net_profit"] == 0

    def test_zero_division_safety(self):
        """Ensure the system handles a zero purchase price without crashing"""
        result = calculate_flip_score(purchase_price=0, resale_value=5000, repair_cost=0)
        assert result["roi"] == 0


class TestSortingAndRanking:
    """Tests for ranking and sorting logic based on ROI"""
    
    def test_sorts_by_roi_descending(self):
        """Should allow sorting results by ROI from highest to lowest"""
        # Generate three scenarios with different ROI
        data = [
            calculate_flip_score(10000, 11000), # 10% ROI
            calculate_flip_score(10000, 13000), # 30% ROI
            calculate_flip_score(10000, 12000), # 20% ROI
        ]
        
        # Sort by ROI descending
        sorted_data = sorted(data, key=lambda x: x["roi"], reverse=True)
        
        assert sorted_data[0]["roi"] == 30.0
        assert sorted_data[1]["roi"] == 20.0
        assert sorted_data[2]["roi"] == 10.0