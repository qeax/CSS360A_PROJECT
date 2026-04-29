/**
 * Global store for the current vehicle list
 */
let vehicles = [];

/**
 * Maps ROI value to a color gradient (Heatmap)
 * Red (0°) for low/negative -> Green (120°) for high ROI
 */
function getHeatmapColor(roi) {
    // Clamp value between 0 and 30 for the gradient scale
    const weight = Math.min(Math.max(roi, 0), 30);
    const hue = (weight / 30) * 120; 
    return `hsl(${hue}, 70%, 50%)`;
}

/**
 * Fetch data from backend API with filters
 */
async function loadVehicles() {
    const brand = document.getElementById('brandSearch').value;
    const price = document.getElementById('priceSearch').value;

    const url = new URL('/api/cars', window.location.origin);
    if (brand) url.searchParams.append('brand', brand);
    if (price) url.searchParams.append('max_price', price);

    try {
        const response = await fetch(url);
        vehicles = await response.json();
        renderTable(vehicles);
    } catch (err) {
        console.error("API Error:", err);
    }
}

/**
 * Renders the scrollable list entries
 */
function renderTable(data) {
    const container = document.getElementById('carList');
    
    container.innerHTML = data.map(car => {
        const roiColor = getHeatmapColor(car.roi);
        return `
            <div class="car-item" onclick="showDetails(${car.id})">
                <div class="car-info">
                    <div class="model">${car.model}</div>
                    <div class="brand">${car.brand}</div>
                </div>
                <div class="year">${car.year}</div>
                <div class="price">$${car.price.toLocaleString()}</div>
                <div class="roi-badge" style="background: ${roiColor}20; color: ${roiColor}">
                    ${car.roi}%
                </div>
            </div>
        `;
    }).join('');
}

/**
 * Modal control
 */
function showDetails(id) {
    const car = vehicles.find(v => v.id === id);
    if (!car) return;

    document.getElementById('mTitle').innerText = `${car.brand} ${car.model}`;
    document.getElementById('mBody').innerHTML = `
        <p>Year: ${car.year}</p>
        <p>Purchase: $${car.price.toLocaleString()}</p>
        <p>Repairs: $${car.repair_cost.toLocaleString()}</p>
        <hr style="border:0; border-top:1px solid #eee">
        <h3>Estimated Profit: $${car.net_profit.toLocaleString()}</h3>
    `;
    document.getElementById('detailModal').style.display = 'flex';
}

function closeModal() {
    document.getElementById('detailModal').style.display = 'none';
}

/**
 * Debounced search event listeners
 */
let timer;
document.querySelectorAll('input').forEach(el => {
    el.addEventListener('input', () => {
        clearTimeout(timer);
        timer = setTimeout(loadVehicles, 300);
    });
});

// Initial load on startup
loadVehicles();