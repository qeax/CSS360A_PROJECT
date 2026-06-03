/**
 * Shared shell: theme, session check, account menu, toolbar profile UI.
 */

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
};

function getSettings() {
    try {
        const raw = localStorage.getItem(CSS360_SETTINGS_KEY);
        if (!raw) return { ...CSS360_SETTINGS_DEFAULTS };
        const parsed = JSON.parse(raw);
        return {
            showListingJsonDebug: Boolean(parsed.showListingJsonDebug),
            showDeleteCarButton: Boolean(parsed.showDeleteCarButton),
        };
    } catch {
        return { ...CSS360_SETTINGS_DEFAULTS };
    }
}

function saveSettings(partial) {
    const next = { ...getSettings(), ...partial };
    localStorage.setItem(
        CSS360_SETTINGS_KEY,
        JSON.stringify({
            showListingJsonDebug: Boolean(next.showListingJsonDebug),
            showDeleteCarButton: Boolean(next.showDeleteCarButton),
        }),
    );
}

function initAppShell() {
    initTheme();
    initThemeToggle();
    initAccountMenu();
}
