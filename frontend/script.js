/**
 * CSS360 Car Flip Dashboard - Frontend Logic
 */

/** Stub session flag — must match login.js until real auth exists. */
const AUTH_STORAGE_KEY = 'css360_authenticated';
const AUTH_STORAGE_VALUE = '1';

// Global state
let carData = [];
let currentResults = [];

// ============= THEME MANAGEMENT =============
function toggleTheme() {
    document.body.classList.toggle('light-theme');
    const isLight = document.body.classList.contains('light-theme');
    localStorage.setItem('theme', isLight ? 'light' : 'dark');
}

// Load saved theme on startup
function initTheme() {
    if (localStorage.getItem('theme') === 'light') {
        document.body.classList.add('light-theme');
    }
}

// ============= HEATMAP CALCULATION =============
function calculateHeatmap(roi, brightness = 45, saturation = 70) {
    const score = Math.min(Math.max(roi, 0), 30);
    const hue = (score / 30) * 120; // 0 = red, 120 = green
    return `hsl(${hue}, ${saturation}%, ${brightness}%)`;
}

// ============= API SEARCH =============
async function executeSearch() {
    const list = document.getElementById('inventoryList');
    
    // Collect filter values
    const make = document.getElementById('makeSearch').value.trim();
    const model = document.getElementById('modelSearch').value.trim();
    const maxPrice = document.getElementById('maxPrice').value.trim();

    // Loading state
    list.style.opacity = "0.5";
    list.innerHTML = '<div class="loading">Loading inventory...</div>';

    // Build query URL
    const query = new URL('/api/cars', window.location.origin);
    
    if (make) query.searchParams.append('make', make);
    if (model) query.searchParams.append('model', model);
    if (maxPrice) query.searchParams.append('max_price', maxPrice);

    try {
        const response = await fetch(query);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        carData = await response.json();
        currentResults = [...carData]; // Clone for frontend sorting
        sortResults();
    } catch (err) {
        console.error("Search failed:", err);
        list.innerHTML = `
            <div style='padding: 40px; text-align: center;'>
                <div style='color: #ef4444; font-size: 18px; margin-bottom: 10px;'>Connection Error</div>
                <div style='color: var(--text-muted);'>Unable to reach backend. Check if server is running.</div>
            </div>
        `;
    } finally {
        list.style.opacity = "1";
    }
}

// ============= FRONTEND SORTING =============
function sortResults() {
    const sortBy = document.getElementById('frontendSortBy').value;
    const sortOrder = document.getElementById('frontendSortOrder').value;
    const reverse = sortOrder === 'desc';

    currentResults.sort((a, b) => {
        let aVal, bVal;
        
        switch(sortBy) {
            case 'net_profit':
                aVal = a.net_profit;
                bVal = b.net_profit;
                break;
            case 'price':
                aVal = a.price;
                bVal = b.price;
                break;
            case 'roi':
            default:
                aVal = a.roi;
                bVal = b.roi;
                break;
        }
        
        return reverse ? bVal - aVal : aVal - bVal;
    });

    updateUI(currentResults);
}

// ============= UI RENDERING =============
function updateUI(items) {
    const list = document.getElementById('inventoryList');
    
    if (items.length === 0) {
        list.innerHTML = `
            <div class="no-results">
                <div>No matches found. Try adjusting your filters.</div>
            </div>
        `;
        return;
    }

    list.innerHTML = items.map(car => {
        const heatmapColor = calculateHeatmap(car.roi, 45, 70);
        const heatmapColorBorder = calculateHeatmap(car.roi, 35, 60);

        const imageBlock = car.image_url
            ? `<img src="${car.image_url}" alt="">`
            : 'Image Placeholder';

        return `
            <div class="car-card" data-car-id="${car.id}">
                <div class="car-image">
                    ${imageBlock}
                </div>
                <div class="car-info">
                    <div class="car-header-row">
                        <div class="car-year-pill">${car.year}</div>
                        <h3 class="car-model">${car.brand} ${car.model}</h3>
                    </div>
                    
                    <div class="separator"></div>
                    
                    <div class="stats-grid">
                        <div class="stat-box">
                            <span class="stat-label">Mileage</span>
                            <span class="stat-value">${car.mileage ? car.mileage.toLocaleString() : 'N/A'} mi</span>
                        </div>
                        <div class="stat-box">
                            <span class="stat-label">Condition</span>
                            <span class="stat-value">${car.condition ?? 'Undefined'}</span>
                        </div>
                        <div class="stat-box">
                            <span class="stat-label">Purchase Price</span>
                            <span class="stat-value">$${car.price.toLocaleString()}</span>
                        </div>
                        <div class="stat-box">
                            <span class="stat-label">ROI</span>
                            <div class="roi-pill" style="background-color: ${heatmapColor}; border-color: ${heatmapColorBorder};">
                                ${car.roi}%
                            </div>
                        </div>
                        <div class="stat-box">
                            <span class="stat-label">Net Profit</span>
                            <span class="stat-value" style="color: ${car.net_profit >= 0 ? 'var(--accent-green)' : '#ef4444'};">
                                ${car.net_profit >= 0 ? '+' : ''}$${car.net_profit.toLocaleString()}
                            </span>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }).join('');

    // Add click listeners to cards
    document.querySelectorAll('.car-card').forEach(card => {
        card.addEventListener('click', function() {
            const carId = parseInt(this.dataset.carId);
            const car = items.find(c => c.id === carId);
            if (car) showCarDetails(car);
        });
    });
}

// ============= MODAL MANAGEMENT =============
function showCarDetails(car) {
    const modal = document.getElementById('itemModal');
    const header = document.getElementById('modalHeader');
    const content = document.getElementById('modalContent');

    header.textContent = `${car.brand} ${car.model} (${car.year})`;
    
    content.innerHTML = `
        <div style="display: flex; flex-direction: column; gap: 16px;">
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                <div>
                    <div style="color: var(--text-muted); font-size: 12px; margin-bottom: 4px;">PURCHASE PRICE</div>
                    <div style="font-size: 20px; font-weight: 700;">$${car.price.toLocaleString()}</div>
                </div>
                <div>
                    <div style="color: var(--text-muted); font-size: 12px; margin-bottom: 4px;">RESALE VALUE</div>
                    <div style="font-size: 20px; font-weight: 700;">$${car.resale_value.toLocaleString()}</div>
                </div>
                <div>
                    <div style="color: var(--text-muted); font-size: 12px; margin-bottom: 4px;">REPAIR COST</div>
                    <div style="font-size: 20px; font-weight: 700;">$${car.repair_cost.toLocaleString()}</div>
                </div>
                <div>
                    <div style="color: var(--text-muted); font-size: 12px; margin-bottom: 4px;">MILEAGE</div>
                    <div style="font-size: 20px; font-weight: 700;">${car.mileage ? car.mileage.toLocaleString() : 'N/A'} mi</div>
                </div>
            </div>
            <div style="height: 1px; background: var(--separator);"></div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                <div style="background: var(--bg-page); padding: 12px; border-radius: 8px;">
                    <div style="color: var(--text-muted); font-size: 12px; margin-bottom: 4px;">NET PROFIT</div>
                    <div style="font-size: 24px; font-weight: 700; color: ${car.net_profit >= 0 ? 'var(--accent-green)' : '#ef4444'};">
                        ${car.net_profit >= 0 ? '+' : ''}$${car.net_profit.toLocaleString()}
                    </div>
                </div>
                <div style="background: var(--bg-page); padding: 12px; border-radius: 8px;">
                    <div style="color: var(--text-muted); font-size: 12px; margin-bottom: 4px;">ROI</div>
                    <div style="font-size: 24px; font-weight: 700; color: ${car.roi >= 0 ? 'var(--accent-green)' : '#ef4444'};">
                        ${car.roi}%
                    </div>
                </div>
            </div>
        </div>
    `;

    modal.classList.add('active');
}

function hideModal() {
    document.getElementById('itemModal').classList.remove('active');
}

// ============= EVENT LISTENERS =============
function initEventListeners() {
    document.getElementById('logoutBtn').addEventListener('click', () => {
        localStorage.removeItem(AUTH_STORAGE_KEY);
        window.location.href = '/';
    });

    // Theme toggle
    document.getElementById('themeToggleBtn').addEventListener('click', toggleTheme);
    
    // Search button
    document.getElementById('searchBtn').addEventListener('click', executeSearch);
    
    // Frontend sort controls
    document.getElementById('frontendSortBy').addEventListener('change', sortResults);
    document.getElementById('frontendSortOrder').addEventListener('change', sortResults);
    
    // Close modal
    document.getElementById('closeModalBtn').addEventListener('click', hideModal);
    
    // Close modal on outside click
    document.getElementById('itemModal').addEventListener('click', function(e) {
        if (e.target === this) hideModal();
    });
    
    // Enter key on search inputs
    ['makeSearch', 'modelSearch', 'maxPrice'].forEach(id => {
        document.getElementById(id).addEventListener('keypress', function(e) {
            if (e.key === 'Enter') executeSearch();
        });
    });
}

// ============= INITIALIZATION =============
document.addEventListener('DOMContentLoaded', function() {
    if (localStorage.getItem(AUTH_STORAGE_KEY) !== AUTH_STORAGE_VALUE) {
        window.location.replace('login.html');
        return;
    }

    initTheme();
    initEventListeners();
    executeSearch(); // Load initial data
});