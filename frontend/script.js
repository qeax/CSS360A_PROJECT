async function fetchCars() {
	
	const container = document.getElementById('cars');
	
    try {
		
        const response = await fetch('/api/cars');
		
		if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
		
        const data = await response.json();
		
        container.innerHTML = data.map(car => `
            <div class="car">
                <strong>${car.brand} ${car.model}</strong>
                <div style="margin-top: 10px; color: #aaa;">
					$${car.price.toLocaleString()}
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Error:', error);
        container.innerHTML = `
            <div class="error">
                Unable to load: ${error.message}
            </div>
        `;
    }
}

fetchCars();