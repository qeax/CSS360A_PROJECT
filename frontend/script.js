async function fetchCars() {
    try {
        const response = await fetch('/api/cars');
        const data = await response.json();
        const container = document.getElementById('cars');
        container.innerHTML = data.map(car => `
            <div class="car">
                <strong>${car.brand} ${car.model}</strong> — $${car.price}
            </div>
        `).join('');
    } catch (e) {
        console.error("Error:", e);
    }
}
fetchCars();