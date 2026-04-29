/**
 * Local cache of car data
 */
let carData = [];

/**
 * Heatmap logic: Red to Green based on ROI
 */
function calculateHeatmap(roi) {
    const score = Math.min(Math.max(roi, 0), 30);
    const hue = (score / 30) * 120; // 0 is red, 120 is green
    return `hsl(${hue}, 70%, 45%)`;
}

/**
 * Primary search function triggered by button or Enter key
 */
async function executeSearch() {
    const list = document.getElementById('inventoryList');
    const brand = document.getElementById('brandSearch').value;
    const maxPrice = document.getElementById('priceFilter').value;
    const minYear = document.getElementById('yearFilter').value;

    // Visual feedback for search button press
    list.style.opacity = "0.5";

    const query = new URL('/api/cars', window.location.origin);
    // Append parameters only if they have values[cite: 8]
    if (brand) query.searchParams.append('brand', brand);
    if (maxPrice) query.searchParams.append('max_price', maxPrice);
    if (minYear) query.searchParams.append('min_year', minYear);

    try {
        const response = await fetch(query);
        if (!response.ok) throw new Error('Backend unreachable');
        
        carData = await response.json();
        updateUI(carData);
    } catch (err) {
        console.error("Search failed:", err);
        list.innerHTML = "<div style='padding: 20px; color: red;'>Connection Error. Check backend status.</div>";
    } finally {
        list.style.opacity = "1";
    }
}

/**
 * Updates the scrollable list with new results
 */
function updateUI(items) {
    const list = document.getElementById('inventoryList');
    if (items.length === 0) {
        list.innerHTML = "<div style='padding: 20px; text-align: center;'>No matches found.</div>";
        return;
    }

    list.innerHTML = items.map(car => {
        const color = calculateHeatmap(car.roi);
        return `
            <div class="car-row" onclick="viewDetails(${car.id})">
                <div>
                    <div class="car-name">${car.brand} ${car.model}</div>
                    <div class="car-sub">ID: #${car.id.toString().padStart(4, '0')}</div>
                </div>
                <div style="font-size: 14px; color: #64748b;">Year: ${car.year}</div>
                <div style="font-weight: 700; color: var(--text-main);">$${car.price.toLocaleString()}</div>
                
                <!-- The ROI Heatmap Pill Element -->
                <div class="roi-pill" style="background-color: ${color}; color: white; border-color: ${color};">
                    ${car.roi}% ROI
                </div>
            </div>
        `;
    }).join('');
}

/**
 * Modal interactions
 */
function viewDetails(id) {
    const car = carData.find(c => c.id === id);
    if (!car) return;

    document.getElementById('modalHeader').innerText = `${car.brand} ${car.model}`;
    document.getElementById('modalContent').innerHTML = `
        <p><strong>Year:</strong> ${car.year}</p>
        <p><strong>Purchase Price:</strong> $${car.price.toLocaleString()}</p>
        <p><strong>Repair Estimate:</strong> $${car.repair_cost.toLocaleString()}</p>
        <p><strong>Resale Value:</strong> $${car.resale_value.toLocaleString()}</p>
        <hr style="border: 0; border-top: 1px solid #f1f5f9; margin: 15px 0;">
        <div style="background: #f8fafc; padding: 15px; border-radius: 10px;">
            <h3 style="margin: 0; color: #059669;">Net Profit: $${car.net_profit.toLocaleString()}</h3>
            <p style="margin: 5px 0 0 0; font-size: 14px; color: #64748b;">ROI calculation: ${(car.roi).toFixed(1)}%</p>
        </div>
    `;
    document.getElementById('itemModal').style.display = 'flex';
}

function hideModal() {
    document.getElementById('itemModal').style.display = 'none';
}

/**
 * Handle "Enter" key on the search bar
 */
document.getElementById('brandSearch').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') executeSearch();
});

// Initial load
executeSearch();