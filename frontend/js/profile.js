/**
 * Profile page — account summary and tracked watchlist.
 */

const PROFILE_VIEW_KEY = 'profile_view';

function getProfileViewMode() {
    return localStorage.getItem(PROFILE_VIEW_KEY) === 'grid' ? 'grid' : 'list';
}

function setProfileViewMode(mode) {
    localStorage.setItem(PROFILE_VIEW_KEY, mode === 'grid' ? 'grid' : 'list');
    const list = document.getElementById('profileWatchlist');
    if (list) {
        list.classList.add('inventory-list');
        list.classList.toggle('inventory-list--grid', mode === 'grid');
    }
    const listBtn = document.getElementById('profileViewListBtn');
    const gridBtn = document.getElementById('profileViewGridBtn');
    if (listBtn) listBtn.setAttribute('aria-pressed', mode === 'list' ? 'true' : 'false');
    if (gridBtn) gridBtn.setAttribute('aria-pressed', mode === 'grid' ? 'true' : 'false');
}

function showProfileToast(message) {
    const stack = document.getElementById('appToastStack');
    if (!stack || !message) return;
    const el = document.createElement('div');
    el.className = 'app-toast app-toast--warn';
    el.setAttribute('role', 'status');
    el.textContent = message;
    stack.appendChild(el);
    window.setTimeout(() => {
        el.classList.add('is-hiding');
        window.setTimeout(() => el.remove(), 400);
    }, 5000);
}

function renderProfilePage(me) {
    const email = me.email || '';
    const displayName = (me.display_name && me.display_name.trim()) || displayNameFromEmail(email);

    const heading = document.getElementById('profileHeading');
    const emailEl = document.getElementById('profileEmail');
    if (heading) heading.textContent = displayName;
    if (emailEl) emailEl.textContent = email;

    applyAvatarToSlot(
        document.getElementById('profileAvatarImg'),
        document.getElementById('profileAvatarFallback'),
        displayName,
        me.profile_picture_url || null,
    );
}

async function removeFromWatchlist(carId, cardEl) {
    const res = await fetch(`/api/watchlist/${carId}`, {
        method: 'DELETE',
        credentials: 'include',
    });
    if (res.status === 204) {
        cardEl.remove();
        const countEl = document.getElementById('profileWatchlistCount');
        const list = document.getElementById('profileWatchlist');
        const remaining = list ? list.querySelectorAll('.car-card').length : 0;
        if (countEl) countEl.textContent = remaining ? `${remaining} / 10` : '';
        if (remaining === 0 && list) {
            list.innerHTML = '<div class="profile-watchlist-empty">No tracked listings yet. Use the heart on inventory cards to track up to 10.</div>';
        }
    }
}

function renderWatchlist(items) {
    const list = document.getElementById('profileWatchlist');
    const countEl = document.getElementById('profileWatchlistCount');
    if (!list) return;

    if (countEl) countEl.textContent = items.length ? `${items.length} / 10` : '';

    const L = window.Css360Listing;
    if (!items.length) {
        list.innerHTML =
            '<div class="profile-watchlist-empty">No tracked listings yet. Use the heart on inventory cards to track up to 10.</div>';
        return;
    }

    list.innerHTML = items
        .map((car) =>
            L.buildCarCardHtml(car, {
                showWatchButton: true,
                isWatched: true,
            }),
        )
        .join('');

    list.querySelectorAll('.car-card').forEach((card) => {
        card.addEventListener('click', (e) => {
            if (
                e.target.closest(
                    '.car-card-carousel-nav, .car-card-carousel-dot, .car-card-listing-link, .car-card-watch-btn',
                )
            ) {
                return;
            }
            const carId = parseCarId(card.dataset.carId);
            if (carId) {
                window.location.href = `/car.html?id=${carId}&return=${encodeURIComponent('profile.html')}`;
            }
        });
    });

    list.querySelectorAll('.car-card-watch-btn').forEach((btn) => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const carId = Number(btn.dataset.carId);
            const card = btn.closest('.car-card');
            if (carId && card) removeFromWatchlist(carId, card);
        });
    });

    L.initCarouselsIn(list);
}

async function loadWatchlist() {
    const res = await fetch('/api/watchlist', { credentials: 'include' });
    if (!res.ok) return [];
    const data = await res.json();
    return data.items || [];
}

document.addEventListener('DOMContentLoaded', async () => {
    initAppShell();
    const me = await requireAuth();
    if (!me) return;

    setNotificationsBadge(me.notifications_unread_count);
    await runWatchCheckIfDue();

    renderProfilePage(me);
    setProfileViewMode(getProfileViewMode());

    document.getElementById('profileViewListBtn')?.addEventListener('click', () => {
        setProfileViewMode('list');
    });
    document.getElementById('profileViewGridBtn')?.addEventListener('click', () => {
        setProfileViewMode('grid');
    });

    const items = await loadWatchlist();
    renderWatchlist(items);
});
