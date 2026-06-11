/**
 * Shared shell: theme, session check, account menu, toolbar profile UI.
 */

/** Positive integer car primary key only (rejects floats, "undefined", "null", etc.). */
function parseCarId(value) {
    if (value == null || value === '') return null;
    const raw = String(value).trim();
    if (!/^\d+$/.test(raw)) return null;
    const id = parseInt(raw, 10);
    return Number.isSafeInteger(id) && id > 0 ? id : null;
}

function initTheme() {
    if (localStorage.getItem('theme') === 'light') {
        document.body.classList.add('light-theme');
    }
}

function toggleTheme() {
    document.body.classList.toggle('light-theme');
    const isLight = document.body.classList.contains('light-theme');
    localStorage.setItem('theme', isLight ? 'light' : 'dark');
}

function displayNameFromEmail(email) {
    const local = (email || '').split('@')[0] || '';
    if (!local) return 'User';
    return local.replace(/[._]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function initialsFromName(name) {
    const parts = (name || '').trim().split(/\s+/).filter(Boolean);
    if (parts.length >= 2) {
        return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
    }
    return (parts[0] || '?').slice(0, 2).toUpperCase();
}

function applyAvatarToSlot(imgEl, fallbackEl, displayName, pictureUrl) {
    if (!imgEl || !fallbackEl) return;

    const showImage = Boolean(pictureUrl);
    if (showImage) {
        imgEl.onerror = () => {
            imgEl.onerror = null;
            imgEl.removeAttribute('src');
            imgEl.hidden = true;
            fallbackEl.hidden = false;
            fallbackEl.textContent = initialsFromName(displayName);
        };
        // Session cookie is sent for same-origin avatar URLs (/api/auth/avatar).
        if (pictureUrl.startsWith('/api/')) {
            imgEl.removeAttribute('crossorigin');
        }
        imgEl.src = pictureUrl;
        imgEl.alt = displayName;
        imgEl.hidden = false;
        fallbackEl.hidden = true;
        fallbackEl.textContent = '';
        return;
    }

    imgEl.onerror = null;

    imgEl.removeAttribute('src');
    imgEl.hidden = true;
    fallbackEl.hidden = false;
    fallbackEl.textContent = initialsFromName(displayName);
}

function applyAccountUi(me) {
    const email = me.email || '';
    const displayName = (me.display_name && me.display_name.trim())
        || displayNameFromEmail(email);
    const pictureUrl = me.profile_picture_url || null;

    const nameEl = document.getElementById('accountDisplayName');
    const emailEl = document.getElementById('accountEmailLabel');
    if (nameEl) nameEl.textContent = displayName;
    if (emailEl) emailEl.textContent = email;

    applyAvatarToSlot(
        document.getElementById('accountAvatarImg'),
        document.getElementById('accountAvatarFallback'),
        displayName,
        pictureUrl,
    );

    const trigger = document.getElementById('accountMenuBtn');
    if (trigger) {
        trigger.setAttribute('aria-label', `Account menu for ${displayName}`);
    }
}

async function fetchCurrentUser() {
    const res = await fetch('/api/auth/me', { credentials: 'include' });
    if (res.status === 401) return null;
    if (!res.ok) throw new Error('session_check_failed');
    return res.json();
}

async function requireAuth(redirectTo = 'login.html') {
    try {
        const me = await fetchCurrentUser();
        if (!me) {
            window.location.replace(redirectTo);
            return null;
        }
        applyAccountUi(me);
        return me;
    } catch {
        window.location.replace(redirectTo);
        return null;
    }
}

function initAccountMenu() {
    const wrap = document.getElementById('appAccountWrap');
    const btn = document.getElementById('accountMenuBtn');
    const menu = document.getElementById('accountMenu');
    if (!wrap || !btn || !menu) return;

    btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const open = menu.hidden;
        menu.hidden = !open;
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });

    menu.addEventListener('click', (e) => e.stopPropagation());

    document.addEventListener('click', () => {
        menu.hidden = true;
        btn.setAttribute('aria-expanded', 'false');
    });
}

function initThemeToggle() {
    document.getElementById('themeToggleBtn')?.addEventListener('click', toggleTheme);
}

const CSS360_SETTINGS_KEY = 'css360_settings_v1';

const CSS360_SETTINGS_DEFAULTS = {
    showListingJsonDebug: false,
    showDeleteCarButton: false,
    listingDetailMode: 'page',
};

function getSettings() {
    try {
        const raw = localStorage.getItem(CSS360_SETTINGS_KEY);
        if (!raw) return { ...CSS360_SETTINGS_DEFAULTS };
        const parsed = JSON.parse(raw);
        const mode = parsed.listingDetailMode === 'modal' ? 'modal' : 'page';
        return {
            showListingJsonDebug: Boolean(parsed.showListingJsonDebug),
            showDeleteCarButton: Boolean(parsed.showDeleteCarButton),
            listingDetailMode: mode,
        };
    } catch {
        return { ...CSS360_SETTINGS_DEFAULTS };
    }
}

function saveSettings(partial) {
    const next = { ...getSettings(), ...partial };
    const mode = next.listingDetailMode === 'modal' ? 'modal' : 'page';
    localStorage.setItem(
        CSS360_SETTINGS_KEY,
        JSON.stringify({
            showListingJsonDebug: Boolean(next.showListingJsonDebug),
            showDeleteCarButton: Boolean(next.showDeleteCarButton),
            listingDetailMode: mode,
        }),
    );
}

let notificationsEphemeralBump = 0;
/** @type {Array<object>} client-only preview rows (Settings test button, etc.) */
let ephemeralNotifications = [];

function setNotificationsBadge(count) {
    const badge = document.getElementById('notificationsBadge');
    if (!badge) return;
    const n = (Number(count) || 0) + notificationsEphemeralBump;
    if (n <= 0) {
        badge.hidden = true;
        badge.textContent = '';
        return;
    }
    badge.hidden = false;
    badge.textContent = n > 99 ? '99+' : String(n);
}

async function refreshNotificationsBadge() {
    try {
        const res = await fetch('/api/notifications/unread-count', { credentials: 'include' });
        if (!res.ok) return;
        const data = await res.json();
        setNotificationsBadge(data.unread_count);
    } catch (_) {
        /* ignore */
    }
}

async function runWatchCheckIfDue() {
    try {
        await fetch('/api/watchlist/check', { method: 'POST', credentials: 'include' });
        await refreshNotificationsBadge();
        if (typeof window.reloadNotificationsPanelIfOpen === 'function') {
            await window.reloadNotificationsPanelIfOpen();
        }
    } catch (_) {
        /* ignore */
    }
}

function notificationItemHtml(n) {
    const unread = !n.read_at ? ' is-unread' : '';
    const when = n.created_at ? new Date(n.created_at).toLocaleString() : '';
    const ephemeral = n.ephemeral ? ' data-ephemeral="true"' : '';
    const ephKey = n._ephKey ? ` data-eph-key="${escapeNotificationsText(n._ephKey)}"` : '';
    const idAttr = n.id != null ? ` data-id="${n.id}"` : '';
    return `<button type="button" class="app-notification-item${unread}"${idAttr}${ephemeral}${ephKey} data-car-id="${n.car_id ?? ''}">
        <div class="app-notification-title">${escapeNotificationsText(n.title)}</div>
        <div class="app-notification-message">${escapeNotificationsText(n.message)}</div>
        <div class="app-notification-time">${escapeNotificationsText(when)}</div>
    </button>`;
}

function initNotificationsBell() {
    const btn = document.getElementById('notificationsBtn');
    const panel = document.getElementById('notificationsPanel');
    const list = document.getElementById('notificationsList');
    const readAll = document.getElementById('notificationsReadAllBtn');
    const wrap = btn?.closest('.app-notifications-wrap');
    if (!btn || !panel) return;

    const closePanel = () => {
        panel.hidden = true;
        btn.setAttribute('aria-expanded', 'false');
    };

    const bindNotificationItem = (el) => {
        el.addEventListener('click', async (e) => {
            e.stopPropagation();
            const isEphemeral = el.dataset.ephemeral === 'true';
            const id = el.dataset.id;
            const carId = el.dataset.carId;
            if (isEphemeral) {
                const ephKey = el.dataset.ephKey;
                if (ephKey) {
                    ephemeralNotifications = ephemeralNotifications.filter((n) => n._ephKey !== ephKey);
                }
                el.remove();
                if (notificationsEphemeralBump > 0) {
                    notificationsEphemeralBump -= 1;
                }
                const badge = document.getElementById('notificationsBadge');
                const shown = badge && !badge.hidden ? parseInt(badge.textContent, 10) || 0 : 0;
                const apiBase = Math.max(0, shown - notificationsEphemeralBump);
                setNotificationsBadge(apiBase);
                if (list && !list.querySelector('.app-notification-item')) {
                    list.innerHTML = '<div class="app-notifications-empty">No notifications yet.</div>';
                }
                return;
            }
            if (id) {
                await fetch(`/api/notifications/${id}/read`, {
                    method: 'PATCH',
                    credentials: 'include',
                });
                el.classList.remove('is-unread');
                await refreshNotificationsBadge();
            }
            const parsedCarId = parseCarId(carId);
            if (parsedCarId) {
                closePanel();
                window.location.href = `/car.html?id=${parsedCarId}`;
            }
        });
    };

    const renderNotifications = (items) => {
        if (!list) return;
        if (!items.length) {
            list.innerHTML = '<div class="app-notifications-empty">No notifications yet.</div>';
            return;
        }
        list.innerHTML = items.map((n) => notificationItemHtml(n)).join('');
        list.querySelectorAll('.app-notification-item').forEach(bindNotificationItem);
    };

    const loadNotificationsList = async () => {
        if (!list) return;
        try {
            const res = await fetch('/api/notifications?limit=20', { credentials: 'include' });
            if (!res.ok) {
                list.innerHTML = '<div class="app-notifications-empty">Could not load notifications.</div>';
                return;
            }
            const data = await res.json();
            const merged = [...ephemeralNotifications, ...(data.items || [])];
            renderNotifications(merged);
            notificationsEphemeralBump = ephemeralNotifications.length;
            setNotificationsBadge(data.unread_count);
        } catch (err) {
            list.innerHTML = '<div class="app-notifications-empty">Could not load notifications.</div>';
        }
    };

    window.injectEphemeralNotification = (item) => {
        if (!item) return;
        const row = {
            ...item,
            ephemeral: true,
            _ephKey: `eph-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        };
        ephemeralNotifications.unshift(row);
        if (list) {
            const empty = list.querySelector('.app-notifications-empty');
            const loading = list.querySelector('.app-notifications-loading');
            if (empty) empty.remove();
            if (loading) loading.remove();
            list.insertAdjacentHTML('afterbegin', notificationItemHtml(row));
            const el = list.firstElementChild;
            if (el?.matches?.('.app-notification-item')) bindNotificationItem(el);
        }
        notificationsEphemeralBump = ephemeralNotifications.length;
        const badge = document.getElementById('notificationsBadge');
        const shown = badge && !badge.hidden ? parseInt(badge.textContent, 10) || 0 : 0;
        const apiBase = Math.max(0, shown - (notificationsEphemeralBump - 1));
        setNotificationsBadge(apiBase);
    };

    window.reloadNotificationsPanelIfOpen = async () => {
        const panel = document.getElementById('notificationsPanel');
        if (!panel || panel.hidden) return;
        await loadNotificationsList();
    };

    btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const willOpen = panel.hidden;
        if (willOpen) {
            panel.hidden = false;
            btn.setAttribute('aria-expanded', 'true');
            if (list) {
                list.innerHTML = '<div class="app-notifications-loading">Loading…</div>';
            }
            void loadNotificationsList();
        } else {
            closePanel();
        }
    });

    panel.addEventListener('click', (e) => e.stopPropagation());
    wrap?.addEventListener('click', (e) => e.stopPropagation());

    document.addEventListener('click', (e) => {
        if (wrap?.contains(e.target)) return;
        if (!panel.hidden) closePanel();
    });

    readAll?.addEventListener('click', async (e) => {
        e.stopPropagation();
        await fetch('/api/notifications/read-all', { method: 'POST', credentials: 'include' });
        ephemeralNotifications = [];
        notificationsEphemeralBump = 0;
        await refreshNotificationsBadge();
        if (!panel.hidden) await loadNotificationsList();
    });
}

function escapeNotificationsText(s) {
    return String(s ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function normalizeAppPath(pathname) {
    if (pathname === '/' || pathname.endsWith('/index.html')) return '/index.html';
    return pathname;
}

function initBrandCarHop() {
    const BRAND_HOP_MS = 600;

    document.querySelectorAll('.app-brand').forEach((link) => {
        link.addEventListener('click', (e) => {
            if (e.defaultPrevented) return;
            if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;

            const car = link.querySelector('.app-brand-car');
            if (!car) return;

            e.preventDefault();

            if (link.dataset.brandHopActive === '1') return;
            link.dataset.brandHopActive = '1';

            const href = link.getAttribute('href') || '/index.html';
            let targetPath = '/index.html';
            try {
                targetPath = normalizeAppPath(new URL(href, window.location.href).pathname);
            } catch {
                /* keep default */
            }
            const onHome = normalizeAppPath(window.location.pathname) === targetPath;

            car.classList.remove('app-brand-car--hop');
            void car.offsetWidth;
            car.classList.add('app-brand-car--hop');

            let finished = false;
            const finish = () => {
                if (finished) return;
                finished = true;
                delete link.dataset.brandHopActive;
                car.classList.remove('app-brand-car--hop');
                car.removeEventListener('animationend', onEnd);
                if (onHome) {
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                    return;
                }
                window.location.assign(href);
            };

            const onEnd = (ev) => {
                if (ev.animationName !== 'app-brand-car-hop') return;
                finish();
            };

            car.addEventListener('animationend', onEnd);
            window.setTimeout(finish, BRAND_HOP_MS + 50);
        });
    });
}

function initAppShell() {
    initTheme();
    initThemeToggle();
    initAccountMenu();
    initNotificationsBell();
    initBrandCarHop();
}
