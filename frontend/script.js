/**
 * Global state for loaded vehicles
 */
let currentData = [];

/**
 * Fetches car data from the backend with current filter values
 */
async function fetchCars() {
    const brand = document.getElementById('brandInput').value;
    const maxPrice = document.getElementById('priceInput').value;
    const minYear = document.getElementById('yearInput').value;

    // Build URL with query parameters[cite: 8]
    const url = new URL('/api/cars', window.location.origin);
    if (brand) url.searchParams.append('brand', brand);
    if (maxPrice) url.searchParams.append('max_price', maxPrice);
    if (minYear) url.searchParams.append('min_year', minYear);

    try {
        const response = await fetch(url);
        currentData = await response.json();
        renderList(currentData);
    } catch (error) {
        console.error("Data fetching failed:", error);
    }
}

/**
 * Renders the list of car cards into the grid
 */
function renderList(cars) {
    const container = document.getElementById('cars');
    if (cars.length === 0) {
        container.innerHTML = "<p>No matches found.</p>";
        return;
    }

    container.innerHTML = cars.map(car => `
        <div class="car-card" onclick="openModal(${car.id})">
            <div style="color: var(--text-secondary); font-size: 0.8em;">${car.year}</div>
            <h3 style="margin: 5px 0;">${car.brand} ${car.model}</h3>
            <div>$${car.price.toLocaleString()}</div>
            <div class="roi-tag">ROI: ${car.roi}%</div>
        </div>
    `).join('');
}

/**
 * Handles modal display logic
 */
function openModal(id) {
    const car = currentData.find(c => c.id === id);
    if (!car) return;

    document.getElementById('modalTitle').innerText = `${car.brand} ${car.model}`;
    document.getElementById('modalBody').innerHTML = `
        <p>Purchase: $${car.price.toLocaleString()}</p>
        <p>Repairs: $${car.repair_cost.toLocaleString()}</p>
        <p>Resale: $${car.resale_value.toLocaleString()}</p>
        <hr style="border: 0; border-top: 1px solid #334155;">
        <h3 style="color: var(--accent)">Profit: $${car.net_profit.toLocaleString()}</h3>
    `;
    document.getElementById('carModal').style.display = 'flex';
}

function closeModal() {
    document.getElementById('carModal').style.display = 'none';
}

/**
 * Event listeners with basic debounce for inputs[cite: 8]
 */
let debounceTimer;
['brandInput', 'priceInput', 'yearInput'].forEach(id => {
    document.getElementById(id).addEventListener('input', () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(fetchCars, 400);
    });
});

// Initial data load
fetchCars();