/**
 * CSS360 Car Flip Dashboard — inventory UI, filters, global search.
 */

const VIEW_STORAGE_KEY = 'inventory_view';
const SORT_DESC_KEY = 'inventory_sort_desc';
const PAGE_SIZE = 50;
const INVENTORY_SESSION_KEY = 'css360_inventory_session_v1';
const INVENTORY_SESSION_TTL_MS = 30 * 60 * 1000;
const LOCATION_NOT_SPECIFIED = '__not_specified__';
const LOCATION_NOT_SPECIFIED_LABEL = 'Not specified';
const MAX_CAROUSEL_DOTS = 7;
const YEAR_GAP = 1;
const PRICE_GAP = 100;
const MILEAGE_GAP = 500;

let carData = [];
let currentResults = [];
let listTotal = 0;
let inventoryMeta = null;
let sortDesc = true;
let lastDataMode = 'database';
let auctionCountdownTimerId = null;
/** @type {{ pending_in_batch: number, batch_size: number, wave_size: number, batch_exhausted: boolean, can_fetch_new_batch: boolean } | null} */
let ebayBatchMeta = null;

/** @type {Set<number>} */
let watchlistIds = new Set();

/** Center of a 7-dot strip (the 4th dot, 1-based). */
const CAROUSEL_DOTS_CENTER_IDX = 3;

/** @type {{ countries: Set<string>, regions: Set<string>, cities: Set<string> }} */
const locSelection = {
    countries: new Set(),
    regions: new Set(),
    cities: new Set(),
};

/** @type {Set<string>} */
const makeSelection = new Set();

const DELIVERY_CHIPS = [
    { value: 'ship', label: 'Ship to home' },
    { value: 'local_pickup', label: 'Local pickup' },
    { value: 'in_store', label: 'In-store pickup' },
];

const FILTER_BODY_STYLES = [
    'Commercial Vehicle',
    'Convertible',
    'Coupe',
    'Hatchback',
    'Minivan',
    'Sedan',
    'SUV',
    'Wagon',
    'Not Specified',
];

const FILTER_CONDITIONS = ['New', 'Pre-owned', 'Used'];

const FILTER_LISTING_FORMATS = [
    { value: 'AUCTION', label: 'Auction' },
    { value: 'BUY_IT_NOW', label: 'Buy it now' },
    { value: 'CLASSIFIED_AD', label: 'Classified ads' },
    { value: 'ACCEPTS_OFFER', label: 'Accepts offer' },
];

const FILTER_VEHICLE_TITLES = [
    'Clean',
    'Finance Owing/Encumbered',
    'Flood/Water Damage',
    'Lemon & Manufacturer Buyback',
    'Rebuilt/Rebuildable & Reconstructed',
    'Salvage',
    'Not Specified',
];

const LISTING_FORMAT_LABELS = {
    AUCTION: 'Auction',
    BUY_IT_NOW: 'Buy it now',
    FIXED_PRICE: 'Buy it now',
    CLASSIFIED_AD: 'Classified ads',
    ACCEPTS_OFFER: 'Accepts offer',
};

function initViewMode() {
    const el = document.getElementById('inventoryList');
    const mode = localStorage.getItem(VIEW_STORAGE_KEY) || 'list';
    el.classList.add('inventory-list');
    el.classList.toggle('inventory-list--grid', mode === 'grid');
    const listBtn = document.getElementById('viewListBtn');
    const gridBtn = document.getElementById('viewGridBtn');
    if (listBtn && gridBtn) {
        listBtn.setAttribute('aria-pressed', mode === 'list' ? 'true' : 'false');
        gridBtn.setAttribute('aria-pressed', mode === 'grid' ? 'true' : 'false');
    }
}

function setViewMode(mode) {
    const el = document.getElementById('inventoryList');
    localStorage.setItem(VIEW_STORAGE_KEY, mode);
    el.classList.toggle('inventory-list--grid', mode === 'grid');
    document.getElementById('viewListBtn').setAttribute('aria-pressed', mode === 'list' ? 'true' : 'false');
    document.getElementById('viewGridBtn').setAttribute('aria-pressed', mode === 'grid' ? 'true' : 'false');
}

function initSortOrderUi() {
    const stored = localStorage.getItem(SORT_DESC_KEY);
    sortDesc = stored !== 'false';
    applySortOrderClass();
}

function applySortOrderClass() {
    document.body.classList.toggle('sort-desc', sortDesc);
    document.body.classList.toggle('sort-asc', !sortDesc);
    const btn = document.getElementById('sortOrderToggle');
    if (btn) {
        btn.setAttribute('aria-label', sortDesc ? 'Sort direction: descending' : 'Sort direction: ascending');
        btn.setAttribute('title', sortDesc ? 'Highest first' : 'Lowest first');
    }
}

function toggleSortOrder() {
    sortDesc = !sortDesc;
    localStorage.setItem(SORT_DESC_KEY, sortDesc ? 'true' : 'false');
    applySortOrderClass();
    executeSearch({ append: false });
}

function calculateHeatmap(roi, brightness = 42, saturation = 65) {
    const score = Math.min(Math.max(roi, 0), 30);
    const hue = (score / 30) * 120;
    return `hsl(${hue}, ${saturation}%, ${brightness}%)`;
}

function calculateHeatmapBorder(roi) {
    return calculateHeatmap(roi, 32, 55);
}

/** Background + border for metrics block from ROI score. */
function metricsBlockHeatStyle(roi, priceKnown = true) {
    if (priceKnown === false || roi == null || Number.isNaN(Number(roi))) {
        return 'background: var(--bg-page); border-color: var(--border-color);';
    }
    const heat = calculateHeatmap(roi, 40, 58);
    const border = calculateHeatmapBorder(roi);
    return `background: color-mix(in srgb, ${heat} 22%, var(--bg-page)); border-color: color-mix(in srgb, ${border} 55%, var(--border-color));`;
}

function isPriceKnown(car) {
    return car && car.price_known !== false;
}

function shouldShowEconomics(car) {
    return isPriceKnown(car) && !car.auction_ended;
}

/**
 * @param {string} message
 * @param {{ variant?: 'error' | 'warn', durationMs?: number }} [opts]
 */
function showEbayToast(message, opts = {}) {
    const stack = document.getElementById('appToastStack');
    if (!stack || !message) return;
    const variant = opts.variant === 'warn' ? 'warn' : 'error';
    const el = document.createElement('div');
    el.className = `app-toast app-toast--${variant}`;
    el.setAttribute('role', 'status');
    el.textContent = message;
    stack.appendChild(el);
    const duration = opts.durationMs ?? 5000;
    window.setTimeout(() => {
        el.classList.add('is-hiding');
        window.setTimeout(() => el.remove(), 400);
    }, duration);
}

function resolveEbayBatchMeta(payload) {
    if (payload?.ebay_batch) return payload.ebay_batch;
    if (payload?.ebay_sync?.ebay_batch) return payload.ebay_sync.ebay_batch;
    return ebayBatchMeta;
}

function loadMoreUsesEbayBatch() {
    if (!ebayBatchMeta) return false;
    if (ebayBatchMeta.pending_in_batch > 0) return true;
    if (carData.length >= listTotal && ebayBatchMeta.can_fetch_new_batch) return true;
    return false;
}

function formatRoiDisplay(car) {
    if (!isPriceKnown(car) || car.roi == null || Number.isNaN(Number(car.roi))) {
        return 'Unable to determine';
    }
    return `${Number(car.roi).toFixed(1)}%`;
}

function formatProfitDisplay(car) {
    if (!isPriceKnown(car) || car.net_profit == null || Number.isNaN(Number(car.net_profit))) {
        return 'Unable to determine';
    }
    return formatMoney(car.net_profit);
}

function metricsBlockHtml(car) {
    if (!shouldShowEconomics(car)) {
        return '';
    }
    const roiLabel = (car.source || '').toLowerCase() === 'ebay' ? 'ROI (est.)' : 'ROI';
    const profitCls = profitValueClass(car.net_profit);
    return `<div class="car-card-metrics-compact" style="${metricsBlockHeatStyle(car.roi, true)}">
            <div class="car-card-metrics-col car-card-metrics-col--roi">
                <span class="car-card-metrics-col-label">${escapeHtml(roiLabel)}</span>
                <span class="car-card-metrics-col-value car-card-metrics-col-value--roi">${escapeHtml(formatRoiDisplay(car))}</span>
            </div>
            <span class="car-card-metrics-divider" aria-hidden="true"></span>
            <div class="car-card-metrics-col car-card-metrics-col--profit">
                <span class="car-card-metrics-col-label">Est. net profit</span>
                <span class="car-card-metrics-col-value ${profitCls}">${escapeHtml(formatProfitDisplay(car))}</span>
            </div>
        </div>`;
}

function formatMoney(n) {
    if (n == null || Number.isNaN(n)) return '—';
    const rounded = Math.round(n);
    const sign = rounded >= 0 ? '+' : '−';
    return `${sign}$${Math.abs(rounded).toLocaleString()}`;
}

function profitValueClass(n) {
    if (n == null || Number.isNaN(n) || n === 0) return '';
    return n > 0 ? 'car-card-metrics-col-value--positive' : 'car-card-metrics-col-value--negative';
}

function formatPriceShort(n) {
    return `$${Math.round(Number(n)).toLocaleString()}`;
}

function deliverySummary(d) {
    if (!d) return 'Delivery: —';
    const parts = [];
    if (d.ship_to_home) parts.push('Ship');
    if (d.local_pickup) parts.push('Local pickup');
    if (d.in_store_pickup) parts.push('In-store');
    return parts.length ? `Delivery: ${parts.join(' · ')}` : 'Delivery: —';
}

function listingFormatLabel(raw) {
    if (raw == null || raw === '') return '—';
    const u = String(raw)
        .trim()
        .toUpperCase()
        .replace(/-/g, '_')
        .replace(/\s+/g, '_');
    if (LISTING_FORMAT_LABELS[u]) return LISTING_FORMAT_LABELS[u];
    // Mirror backend: "ACCEPTS_OFFER" contains "AUCTION" as substring — offers first.
    if (u.includes('ACCEPT') && u.includes('OFFER')) return 'Accepts offer';
    if (u.includes('CLASSIFIED')) return 'Classified ads';
    if (u.includes('AUCTION')) return 'Auction';
    if (u.includes('FIXED') || u.includes('BUYITNOW') || (u.includes('BUY') && u.includes('NOW'))) return 'Buy it now';
    return String(raw).trim();
}

function normalizeListingFormatKey(raw) {
    if (raw == null || raw === '') return '';
    return String(raw)
        .trim()
        .toUpperCase()
        .replace(/-/g, '_')
        .replace(/\s+/g, '_');
}

function formatAuctionCountdown(iso) {
    if (!iso) return '';
    const end = new Date(iso);
    if (Number.isNaN(end.getTime())) return '';
    const ms = Math.max(0, end.getTime() - Date.now());
    if (ms <= 0) return 'Ended';
    const totalSec = Math.floor(ms / 1000);
    const days = Math.floor(totalSec / 86400);
    const h = Math.floor((totalSec % 86400) / 3600);
    const m = Math.floor((totalSec % 3600) / 60);
    const s = totalSec % 60;
    const pad = (n) => String(n).padStart(2, '0');
    const time = `${pad(h)}:${pad(m)}:${pad(s)}`;
    if (days > 0) return `${days}d ${time}`;
    return time;
}

function stopAuctionCountdownTimer() {
    if (window.Css360Listing?.stopAuctionCountdownTimer) {
        window.Css360Listing.stopAuctionCountdownTimer();
        return;
    }
    if (auctionCountdownTimerId != null) {
        clearInterval(auctionCountdownTimerId);
        auctionCountdownTimerId = null;
    }
}

function tickAuctionCountdowns() {
    document.querySelectorAll('#inventoryList [data-countdown-end]').forEach((el) => {
        const iso = el.getAttribute('data-countdown-end');
        if (!iso) return;
        const end = new Date(iso);
        if (Number.isNaN(end.getTime())) return;
        if (end.getTime() <= Date.now()) {
            el.textContent = 'Ended';
            el.removeAttribute('data-countdown-end');
            return;
        }
        el.textContent = formatAuctionCountdown(iso);
    });
}

function ensureAuctionCountdownTimer() {
    if (window.Css360Listing?.startAuctionCountdownTimer) {
        window.Css360Listing.startAuctionCountdownTimer();
        return;
    }
    stopAuctionCountdownTimer();
    if (!document.querySelector('#inventoryList [data-countdown-end]')) return;
    tickAuctionCountdowns();
    auctionCountdownTimerId = setInterval(tickAuctionCountdowns, 1000);
}

/** Footer meta next to price: { text, showSep } */
function formatListingMeta(car) {
    const u = normalizeListingFormatKey(car.listing_format);
    if (!u) return { text: '', showSep: false };
    if (u === 'ACCEPTS_OFFER') return { text: 'or Best Offer', showSep: false };
    if (u === 'BUY_IT_NOW') return { text: 'Buy It Now', showSep: true };
    if (u === 'CLASSIFIED_AD') return { text: 'Classified Ad with Best Offer', showSep: true };
    if (u === 'AUCTION' || u.includes('AUCTION')) {
        const bids = car.bid_count != null ? Number(car.bid_count) : 0;
        const bidLabel = `${bids} bid${bids === 1 ? '' : 's'}`;
        if (car.auction_ended) {
            return { text: bidLabel, showSep: true };
        }
        if (car.listing_ends_at) {
            const left = formatAuctionCountdown(car.listing_ends_at);
            return {
                text: bidLabel,
                countdownIso: car.listing_ends_at,
                countdownText: left,
                showSep: true,
            };
        }
        return { text: bidLabel, showSep: true };
    }
    return { text: listingFormatLabel(car.listing_format), showSep: true };
}

function formatMileageLabel(car) {
    if (car.mileage == null) return 'Mileage unknown';
    return `${Number(car.mileage).toLocaleString()} mi`;
}

function carSubtitleLine(car) {
    const cond = car.condition || '—';
    return `${cond} · ${formatMileageLabel(car)}`;
}

function listingMetaHtml(meta) {
    if (!meta.text && !meta.countdownIso) return '';
    let inner = '';
    if (meta.text) {
        inner += meta.showSep
            ? `<span class="car-card-listing-meta">${escapeHtml(meta.text)}</span>`
            : `<span class="car-card-listing-meta car-card-listing-meta--inline">${escapeHtml(meta.text)}</span>`;
    }
    if (meta.countdownIso && meta.countdownText) {
        if (inner) inner += '<span class="car-card-listing-meta"> · </span>';
        inner += `<span class="car-card-auction-countdown" data-countdown-end="${escapeAttr(meta.countdownIso)}">${escapeHtml(meta.countdownText)}</span>`;
    }
    return inner;
}

function priceBlockHtml(car) {
    const meta = formatListingMeta(car);
    const sep =
        (meta.text || meta.countdownIso) && meta.showSep
            ? '<span class="car-card-price-sep" aria-hidden="true">|</span>'
            : '';
    const metaHtml = listingMetaHtml(meta);
    if (car.auction_ended) {
        return `<div class="car-card-price-block"><span class="car-card-auction-ended-pill">Auction ended</span>${sep}${metaHtml}</div>`;
    }
    if (!isPriceKnown(car)) {
        return `<div class="car-card-price-block"><span class="car-card-price-unknown">Price unavailable</span>${sep}${metaHtml}</div>`;
    }
    return `<div class="car-card-price-block"><span class="car-card-price">$${Number(car.price).toLocaleString()}</span>${sep}${metaHtml}</div>`;
}

function modalPurchasePriceHtml(car) {
    if (car.auction_ended) {
        return '<span class="car-card-auction-ended-pill car-card-auction-ended-pill--modal">Auction ended</span>';
    }
    if (!isPriceKnown(car)) {
        return '<span class="car-card-price-unknown car-card-price-unknown--modal">Price unavailable</span>';
    }
    return `$${Number(car.price).toLocaleString()}`;
}

function buildChipGroup(containerId, items, getValue, getLabel) {
    const el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML = items
        .map(
            (item) => `
        <button type="button" class="filter-chip" data-value="${escapeAttr(getValue(item))}" aria-pressed="false">
            ${escapeHtml(getLabel(item))}
        </button>`
        )
        .join('');
    el.querySelectorAll('.filter-chip').forEach((btn) => {
        btn.addEventListener('click', () => {
            const pressed = btn.getAttribute('aria-pressed') === 'true';
            btn.setAttribute('aria-pressed', pressed ? 'false' : 'true');
        });
    });
}

function escapeHtml(s) {
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, '&#39;');
}

function getSelectedChipValues(containerId) {
    const root = document.getElementById(containerId);
    if (!root) return [];
    return Array.from(root.querySelectorAll('.filter-chip[aria-pressed="true"]')).map((b) => b.dataset.value);
}

function clearLocationSelections() {
    locSelection.countries.clear();
    locSelection.regions.clear();
    locSelection.cities.clear();
    updateLocationTriggerLabels();
    updateLocationTierUi();
}

function updateMakeTriggerLabel() {
    const btn = document.getElementById('filterMakeBtn');
    if (!btn) return;
    const n = makeSelection.size;
    if (!n) btn.textContent = 'Any';
    else if (n === 1) btn.textContent = Array.from(makeSelection)[0];
    else btn.textContent = `${n} makes`;
}

function updateLocationTriggerLabels() {
    const cBtn = document.getElementById('filterCountryBtn');
    const rBtn = document.getElementById('filterRegionBtn');
    const cityBtn = document.getElementById('filterCityBtn');
    if (cBtn) cBtn.textContent = summarizeSet(locSelection.countries, 'country');
    if (rBtn) rBtn.textContent = summarizeSet(locSelection.regions, 'region');
    if (cityBtn) cityBtn.textContent = summarizeCityButton();
}

function summarizeSet(set, kind) {
    const n = set.size;
    if (!n) return 'Any';
    const named = Array.from(set).filter((v) => v !== LOCATION_NOT_SPECIFIED);
    const hasNs = set.has(LOCATION_NOT_SPECIFIED);
    if (n === 1) {
        if (hasNs) return LOCATION_NOT_SPECIFIED_LABEL;
        const v = named[0];
        return v.length > 22 ? `${v.slice(0, 20)}…` : v;
    }
    if (hasNs && named.length === 0) return LOCATION_NOT_SPECIFIED_LABEL;
    if (hasNs) return `${named.length} + ${LOCATION_NOT_SPECIFIED_LABEL}`;
    return `${n} ${kind}${n === 1 ? '' : 's'}`;
}

function summarizeCityButton() {
    const n = locSelection.cities.size;
    if (!n) return 'Any';
    if (n === 1) {
        const k = Array.from(locSelection.cities)[0];
        if (k === LOCATION_NOT_SPECIFIED) return LOCATION_NOT_SPECIFIED_LABEL;
        const parts = k.split('|');
        const name = parts[2] || k;
        return name.length > 22 ? `${name.slice(0, 20)}…` : name;
    }
    return summarizeSet(locSelection.cities, 'city');
}

function locationNotSpecifiedCheckboxRow(kind, checked) {
    return `
        <label class="filter-select-row filter-select-row--not-specified">
            <input type="checkbox" class="filter-select-input" data-loc-kind="${kind}" value="${LOCATION_NOT_SPECIFIED}" ${checked ? 'checked' : ''} />
            <span class="filter-select-text">${escapeHtml(LOCATION_NOT_SPECIFIED_LABEL)}</span>
            <span class="filter-select-tick" aria-hidden="true"></span>
        </label>`;
}

function getAvailableRegionsList() {
    if (!inventoryMeta || locSelection.countries.size === 0) return [];
    const set = new Set();
    Array.from(locSelection.countries).forEach((c) => {
        (inventoryMeta.regions_by_country[c] || []).forEach((r) => set.add(r));
    });
    return Array.from(set).sort((a, b) => a.localeCompare(b));
}

function getAvailableCityRows() {
    if (!inventoryMeta || locSelection.countries.size === 0 || locSelection.regions.size === 0) return [];
    const rbc = inventoryMeta.regions_by_country || {};
    const cbr = inventoryMeta.cities_by_region || {};
    const rows = [];
    Array.from(locSelection.countries).forEach((co) => {
        const allRegsForCo = rbc[co] || [];
        const regLoop = Array.from(locSelection.regions).filter((r) => allRegsForCo.includes(r));
        regLoop.forEach((reg) => {
            const key = `${co}|${reg}`;
            (cbr[key] || []).forEach((city) => {
                rows.push({ full: `${co}|${reg}|${city}`, city });
            });
        });
    });
    rows.sort((a, b) => a.city.localeCompare(b.city));
    return rows;
}

function pruneLocationChildren() {
    const validRegions = new Set(getAvailableRegionsList());
    for (const r of Array.from(locSelection.regions)) {
        if (r === LOCATION_NOT_SPECIFIED) continue;
        if (!validRegions.has(r)) locSelection.regions.delete(r);
    }
    const validCities = new Set(getAvailableCityRows().map((row) => row.full));
    for (const c of Array.from(locSelection.cities)) {
        if (c === LOCATION_NOT_SPECIFIED) continue;
        if (!validCities.has(c)) locSelection.cities.delete(c);
    }
}

function updateLocationTierUi() {
    const hasCountry = locSelection.countries.size > 0;
    const hasRegion = locSelection.regions.size > 0;
    const regionBtn = document.getElementById('filterRegionBtn');
    const cityBtn = document.getElementById('filterCityBtn');
    const regionWrap = document.querySelector('[data-loc-tier="region"]');
    const cityWrap = document.querySelector('[data-loc-tier="city"]');
    if (regionWrap) regionWrap.style.display = hasCountry ? '' : 'none';
    if (cityWrap) cityWrap.style.display = hasRegion ? '' : 'none';
    if (regionBtn) {
        regionBtn.disabled = !hasCountry;
        regionBtn.textContent = hasCountry ? summarizeSet(locSelection.regions, 'region') : 'Select country first';
    }
    if (cityBtn) {
        cityBtn.disabled = !hasRegion;
        cityBtn.textContent = hasRegion ? summarizeCityButton() : 'Select region first';
    }
    if (!hasCountry) {
        locSelection.regions.clear();
        locSelection.cities.clear();
    }
    if (!hasRegion) {
        locSelection.cities.clear();
    }
    updateLocationTriggerLabels();
}

function closeAllFilterDropdownPanels() {
    document.querySelectorAll('.filter-dropdown-panel').forEach((p) => {
        p.hidden = true;
    });
    document.querySelectorAll('.filter-dropdown-trigger').forEach((t) => {
        t.setAttribute('aria-expanded', 'false');
    });
}

function openFilterDropdown(triggerId, panelId, renderFn) {
    closeAllFilterDropdownPanels();
    const trig = document.getElementById(triggerId);
    const panel = document.getElementById(panelId);
    if (!trig || !panel || trig.disabled) return;
    if (renderFn) renderFn();
    panel.hidden = false;
    trig.setAttribute('aria-expanded', 'true');
}

function openLocationPanel(triggerId, panelId) {
    if (panelId === 'filterRegionPanel' && locSelection.countries.size === 0) return;
    if (panelId === 'filterCityPanel' && locSelection.regions.size === 0) return;
    let renderFn = null;
    if (panelId === 'filterCountryPanel') renderFn = renderCountryPanel;
    if (panelId === 'filterRegionPanel') renderFn = renderRegionPanel;
    if (panelId === 'filterCityPanel') renderFn = renderCityPanel;
    openFilterDropdown(triggerId, panelId, renderFn);
}

function renderCountryPanel() {
    const container = document.getElementById('filterCountryChecks');
    if (!container || !inventoryMeta) return;
    const countries = (inventoryMeta.countries || []).filter((c) => c !== LOCATION_NOT_SPECIFIED);
    const nsRow =
        inventoryMeta.location_not_specified?.country
            ? locationNotSpecifiedCheckboxRow('country', locSelection.countries.has(LOCATION_NOT_SPECIFIED))
            : '';
    container.innerHTML =
        nsRow +
        countries
            .map(
                (c) => `
        <label class="filter-select-row">
            <input type="checkbox" class="filter-select-input" data-loc-kind="country" value="${escapeAttr(c)}" ${locSelection.countries.has(c) ? 'checked' : ''} />
            <span class="filter-select-text">${escapeHtml(c)}</span>
            <span class="filter-select-tick" aria-hidden="true"></span>
        </label>`
            )
            .join('');
    wireLocationCheckboxes(container, 'country', () => {
        if (locSelection.countries.size === 0) {
            locSelection.regions.clear();
            locSelection.cities.clear();
        } else {
            pruneLocationChildren();
        }
        refreshRegionOptions();
        refreshCityOptions();
        updateRadiusAvailability();
        updateLocationTierUi();
    });
}

function renderRegionPanel() {
    const container = document.getElementById('filterRegionChecks');
    if (!container || !inventoryMeta) return;
    if (locSelection.countries.size === 0) {
        container.innerHTML = '<div class="filter-dropdown-empty">Select at least one country first.</div>';
        return;
    }
    const sorted = getAvailableRegionsList();
    const nsRow =
        inventoryMeta.location_not_specified?.region
            ? locationNotSpecifiedCheckboxRow('region', locSelection.regions.has(LOCATION_NOT_SPECIFIED))
            : '';
    container.innerHTML =
        nsRow +
        sorted
            .map(
                (r) => `
        <label class="filter-select-row">
            <input type="checkbox" class="filter-select-input" data-loc-kind="region" value="${escapeAttr(r)}" ${locSelection.regions.has(r) ? 'checked' : ''} />
            <span class="filter-select-text">${escapeHtml(r)}</span>
            <span class="filter-select-tick" aria-hidden="true"></span>
        </label>`
            )
            .join('');
    wireLocationCheckboxes(container, 'region', () => {
        if (locSelection.regions.size === 0) {
            locSelection.cities.clear();
        } else {
            pruneLocationChildren();
        }
        refreshCityOptions();
        updateRadiusAvailability();
        updateLocationTierUi();
    });
}

function renderCityPanel() {
    const container = document.getElementById('filterCityChecks');
    if (!container || !inventoryMeta) return;
    if (locSelection.regions.size === 0) {
        container.innerHTML = '<div class="filter-dropdown-empty">Select at least one region first.</div>';
        return;
    }
    const rows = getAvailableCityRows();
    const nsRow =
        inventoryMeta.location_not_specified?.city
            ? locationNotSpecifiedCheckboxRow('city', locSelection.cities.has(LOCATION_NOT_SPECIFIED))
            : '';
    container.innerHTML =
        nsRow +
        rows
            .map(
                ({ full, city }) => `
        <label class="filter-select-row">
            <input type="checkbox" class="filter-select-input" data-loc-kind="city" value="${escapeAttr(full)}" ${locSelection.cities.has(full) ? 'checked' : ''} />
            <span class="filter-select-text">${escapeHtml(city)}</span>
            <span class="filter-select-tick" aria-hidden="true"></span>
        </label>`
            )
            .join('');
    wireLocationCheckboxes(container, 'city', () => {
        updateRadiusAvailability();
        updateLocationTierUi();
    });
}

function renderMakePanel() {
    const container = document.getElementById('filterMakeChecks');
    if (!container || !inventoryMeta) return;
    const makes = inventoryMeta.makes || [];
    container.innerHTML = makes
        .map(
            (m) => `
        <label class="filter-select-row">
            <input type="checkbox" class="filter-select-input" data-make value="${escapeAttr(m)}" ${makeSelection.has(m) ? 'checked' : ''} />
            <span class="filter-select-text">${escapeHtml(m)}</span>
            <span class="filter-select-tick" aria-hidden="true"></span>
        </label>`
        )
        .join('');
    container.querySelectorAll('input[data-make]').forEach((cb) => {
        cb.addEventListener('change', () => {
            if (cb.checked) makeSelection.add(cb.value);
            else makeSelection.delete(cb.value);
            updateMakeTriggerLabel();
        });
    });
}

function wireLocationCheckboxes(container, kind, onChange) {
    container.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
        cb.addEventListener('change', () => {
            const val = cb.value;
            const set =
                kind === 'country' ? locSelection.countries : kind === 'region' ? locSelection.regions : locSelection.cities;
            if (cb.checked) set.add(val);
            else set.delete(val);
            updateLocationTriggerLabels();
            onChange();
        });
    });
}

function initFilterDropdowns() {
    const pairs = [
        ['filterCountryBtn', 'filterCountryPanel'],
        ['filterRegionBtn', 'filterRegionPanel'],
        ['filterCityBtn', 'filterCityPanel'],
        ['filterMakeBtn', 'filterMakePanel'],
    ];
    pairs.forEach(([tid, pid]) => {
        const trig = document.getElementById(tid);
        const panel = document.getElementById(pid);
        if (!trig || !panel) return;
        trig.addEventListener('click', (e) => {
            e.stopPropagation();
            const open = trig.getAttribute('aria-expanded') === 'true';
            if (open) closeAllFilterDropdownPanels();
            else if (pid === 'filterMakePanel') openFilterDropdown(tid, pid, renderMakePanel);
            else openLocationPanel(tid, pid);
        });
    });
    document.querySelectorAll('.filter-dropdown-done').forEach((btn) => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            closeAllFilterDropdownPanels();
        });
    });
    document.addEventListener('click', () => {
        closeAllFilterDropdownPanels();
    });
    document.querySelectorAll('.filter-dropdown').forEach((wrap) => {
        wrap.addEventListener('click', (e) => e.stopPropagation());
    });
}

function populateMetaIntoUi(meta, resetValues = true) {
    inventoryMeta = meta;
    const pmin = document.getElementById('filterPriceMin');
    const pmax = document.getElementById('filterPriceMax');
    const ymin = document.getElementById('filterYearMin');
    const ymax = document.getElementById('filterYearMax');
    const mmin = document.getElementById('filterMileageMin');
    const mmax = document.getElementById('filterMileageMax');
    if (pmin && pmax) {
        let lo = Math.floor(meta.min_price / 100) * 100;
        let hi = Math.ceil(meta.max_price / 100) * 100;
        if (hi <= lo) {
            lo = 0;
            hi = 42500;
        }
        [pmin, pmax].forEach((el) => {
            el.min = String(lo);
            el.max = String(hi);
        });
        if (resetValues) {
            pmin.value = String(lo);
            pmax.value = String(hi);
            updateDualRangeLabels('price', lo, hi);
        }
    }
    if (ymin && ymax) {
        let yLo = Number(meta.min_year);
        let yHi = Number(meta.max_year);
        if (yHi <= yLo) {
            yLo = 2000;
            yHi = 2025;
        }
        ymin.min = String(yLo);
        ymin.max = String(yHi);
        ymax.min = String(yLo);
        ymax.max = String(yHi);
        if (resetValues) {
            ymin.value = String(yLo);
            ymax.value = String(yHi);
            updateDualRangeLabels('year', yLo, yHi);
        }
    }
    if (mmin && mmax && meta.min_mileage != null && meta.max_mileage != null) {
        let lo = Number(meta.min_mileage);
        let hi = Number(meta.max_mileage);
        if (hi <= lo) {
            lo = 8000;
            hi = 145000;
        }
        const step = 500;
        const loR = Math.floor(lo / step) * step;
        const hiR = Math.ceil(hi / step) * step;
        [mmin, mmax].forEach((el) => {
            el.min = String(loR);
            el.max = String(hiR);
        });
        if (resetValues) {
            mmin.value = String(loR);
            mmax.value = String(hiR);
            updateDualRangeLabels('mileage', loR, hiR);
        }
    }

    const chipsMissing = !document.getElementById('filterBodyTypes')?.childElementCount;
    if (resetValues || chipsMissing) {
        buildChipGroup('filterBodyTypes', FILTER_BODY_STYLES, (x) => x, (x) => x);
        buildChipGroup('filterConditions', FILTER_CONDITIONS, (x) => x, (x) => x);
        buildChipGroup(
            'filterListingFormats',
            FILTER_LISTING_FORMATS,
            (x) => x.value,
            (x) => x.label
        );
        buildChipGroup('filterVehicleTitles', FILTER_VEHICLE_TITLES, (x) => x, (x) => x);

        buildChipGroup('filterDelivery', DELIVERY_CHIPS, (x) => x.value, (x) => x.label);
        updateLocationTriggerLabels();
        updateMakeTriggerLabel();
        updateLocationTierUi();
    }
    renderCountryPanel();
    renderMakePanel();
    refreshRegionOptions();
    refreshCityOptions();
}

function updateDualRangeLabels(kind, minV, maxV) {
    if (kind === 'price') {
        const a = document.getElementById('filterPriceMinLabel');
        const b = document.getElementById('filterPriceMaxLabel');
        if (a) a.textContent = formatPriceShort(minV);
        if (b) b.textContent = formatPriceShort(maxV);
    } else if (kind === 'mileage') {
        const a = document.getElementById('filterMileageMinLabel');
        const b = document.getElementById('filterMileageMaxLabel');
        if (a) a.textContent = String(Math.round(minV));
        if (b) b.textContent = String(Math.round(maxV));
    } else {
        const a = document.getElementById('filterYearMinLabel');
        const b = document.getElementById('filterYearMaxLabel');
        if (a) a.textContent = String(Math.round(minV));
        if (b) b.textContent = String(Math.round(maxV));
    }
}

function wireDualRange(kind, minEl, maxEl) {
    if (!minEl || !maxEl) return;
    const gap = kind === 'year' ? YEAR_GAP : kind === 'mileage' ? MILEAGE_GAP : PRICE_GAP;
    const sync = () => {
        const minBound = Number(minEl.min);
        const maxBound = Number(maxEl.max);
        let lo = Number(minEl.value);
        let hi = Number(maxEl.value);
        if (lo > hi) {
            if (document.activeElement === minEl) {
                hi = lo;
            } else {
                lo = hi;
            }
        }
        if (hi - lo < gap) {
            if (document.activeElement === minEl) {
                hi = Math.min(lo + gap, maxBound);
                if (hi - lo < gap) lo = Math.max(hi - gap, minBound);
            } else {
                lo = Math.max(hi - gap, minBound);
                if (hi - lo < gap) hi = Math.min(lo + gap, maxBound);
            }
        }
        minEl.value = String(lo);
        maxEl.value = String(hi);
        updateDualRangeLabels(kind, lo, hi);
    };
    minEl.addEventListener('input', sync);
    maxEl.addEventListener('input', sync);
}

function refreshRegionOptions() {
    renderRegionPanel();
}

function refreshCityOptions() {
    renderCityPanel();
}

function findAnchorForSelectedCities() {
    const meta = inventoryMeta;
    if (!meta) return null;
    const anchors = meta.location_anchors || [];
    for (const key of locSelection.cities) {
        const parts = key.split('|');
        if (parts.length !== 3) continue;
        const [co, reg, city] = parts;
        const hit = anchors.find((a) => a.country === co && a.region === reg && a.city === city);
        if (hit && hit.lat != null && hit.lng != null) return hit;
    }
    return null;
}

function updateRadiusAvailability() {
    const wrap = document.getElementById('radiusFilterWrap');
    const anchor = findAnchorForSelectedCities();
    if (!wrap) return;
    if (anchor) {
        wrap.classList.remove('is-disabled');
        wrap.dataset.anchorLat = String(anchor.lat);
        wrap.dataset.anchorLng = String(anchor.lng);
    } else {
        wrap.classList.add('is-disabled');
        delete wrap.dataset.anchorLat;
        delete wrap.dataset.anchorLng;
    }
}

function appendMultiParams(query, key, values) {
    values.forEach((v) => {
        if (v) query.searchParams.append(key, v);
    });
}

function scrollInventoryToTop() {
    window.scrollTo({ top: 0, behavior: 'smooth' });
    document.querySelector('.inventory-toolbar-strip')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function fetchMeta() {
    const res = await fetch('/api/cars/meta', { credentials: 'include' });
    if (res.status === 401) {
        window.location.replace('login.html');
        return null;
    }
    if (!res.ok) {
        console.warn('fetchMeta failed:', res.status);
        return null;
    }
    return res.json();
}

function collectFilterSnapshot() {
    const radiusWrap = document.getElementById('radiusFilterWrap');
    return {
        globalSearch: document.getElementById('globalSearchInput')?.value ?? '',
        sortBy: document.getElementById('frontendSortBy')?.value ?? 'roi',
        sortDesc,
        locSelection: {
            countries: Array.from(locSelection.countries),
            regions: Array.from(locSelection.regions),
            cities: Array.from(locSelection.cities),
        },
        makes: Array.from(makeSelection),
        chips: {
            filterBodyTypes: getSelectedChipValues('filterBodyTypes'),
            filterConditions: getSelectedChipValues('filterConditions'),
            filterListingFormats: getSelectedChipValues('filterListingFormats'),
            filterVehicleTitles: getSelectedChipValues('filterVehicleTitles'),
            filterDelivery: getSelectedChipValues('filterDelivery'),
        },
        priceMin: document.getElementById('filterPriceMin')?.value ?? '',
        priceMax: document.getElementById('filterPriceMax')?.value ?? '',
        yearMin: document.getElementById('filterYearMin')?.value ?? '',
        yearMax: document.getElementById('filterYearMax')?.value ?? '',
        mileageMin: document.getElementById('filterMileageMin')?.value ?? '',
        mileageMax: document.getElementById('filterMileageMax')?.value ?? '',
        minRoi: document.getElementById('filterMinRoi')?.value ?? '',
        minProfit: document.getElementById('filterMinProfit')?.value ?? '',
        excludeNegativeProfit: document.getElementById('filterExcludeNegativeProfit')?.checked ?? false,
        excludeEndedAuctions: document.getElementById('filterExcludeEndedAuctions')?.checked ?? true,
        excludeUnknownPrice: document.getElementById('filterExcludeUnknownPrice')?.checked ?? false,
        radiusMi: document.getElementById('filterRadiusMi')?.value ?? '',
        anchorLat: radiusWrap?.dataset.anchorLat ?? '',
        anchorLng: radiusWrap?.dataset.anchorLng ?? '',
    };
}

function applyFilterSnapshot(snapshot) {
    if (!snapshot) return;
    const searchInput = document.getElementById('globalSearchInput');
    if (searchInput) searchInput.value = snapshot.globalSearch ?? '';
    const sortEl = document.getElementById('frontendSortBy');
    if (sortEl && snapshot.sortBy) sortEl.value = snapshot.sortBy;
    if (typeof snapshot.sortDesc === 'boolean') {
        sortDesc = snapshot.sortDesc;
        localStorage.setItem(SORT_DESC_KEY, sortDesc ? 'true' : 'false');
        applySortOrderClass();
    }
    locSelection.countries = new Set(snapshot.locSelection?.countries ?? []);
    locSelection.regions = new Set(snapshot.locSelection?.regions ?? []);
    locSelection.cities = new Set(snapshot.locSelection?.cities ?? []);
    makeSelection.clear();
    (snapshot.makes ?? []).forEach((m) => makeSelection.add(m));

    const chipMap = snapshot.chips ?? {};
    Object.entries(chipMap).forEach(([containerId, values]) => {
        const root = document.getElementById(containerId);
        if (!root) return;
        const selected = new Set(values);
        root.querySelectorAll('.filter-chip').forEach((btn) => {
            btn.setAttribute('aria-pressed', selected.has(btn.dataset.value) ? 'true' : 'false');
        });
    });

    const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el && val !== undefined && val !== '') el.value = String(val);
    };
    setVal('filterPriceMin', snapshot.priceMin);
    setVal('filterPriceMax', snapshot.priceMax);
    setVal('filterYearMin', snapshot.yearMin);
    setVal('filterYearMax', snapshot.yearMax);
    setVal('filterMileageMin', snapshot.mileageMin);
    setVal('filterMileageMax', snapshot.mileageMax);
    setVal('filterMinRoi', snapshot.minRoi);
    setVal('filterMinProfit', snapshot.minProfit);
    setVal('filterRadiusMi', snapshot.radiusMi);

    const exProfit = document.getElementById('filterExcludeNegativeProfit');
    if (exProfit) exProfit.checked = !!snapshot.excludeNegativeProfit;
    const exEnded = document.getElementById('filterExcludeEndedAuctions');
    if (exEnded) exEnded.checked = snapshot.excludeEndedAuctions !== false;
    const exUnknown = document.getElementById('filterExcludeUnknownPrice');
    if (exUnknown) exUnknown.checked = !!snapshot.excludeUnknownPrice;

    const radiusWrap = document.getElementById('radiusFilterWrap');
    if (radiusWrap && snapshot.anchorLat && snapshot.anchorLng) {
        radiusWrap.dataset.anchorLat = snapshot.anchorLat;
        radiusWrap.dataset.anchorLng = snapshot.anchorLng;
    }

    updateDualRangeLabels('price', Number(snapshot.priceMin), Number(snapshot.priceMax));
    updateDualRangeLabels('year', Number(snapshot.yearMin), Number(snapshot.yearMax));
    updateDualRangeLabels('mileage', Number(snapshot.mileageMin), Number(snapshot.mileageMax));
    const rlab = document.getElementById('filterRadiusMiLabel');
    if (rlab && snapshot.radiusMi) rlab.textContent = snapshot.radiusMi;

    refreshRegionOptions();
    refreshCityOptions();
    updateRadiusAvailability();
    updateLocationTierUi();
    updateLocationTriggerLabels();
    updateMakeTriggerLabel();
}

function saveInventorySession() {
    try {
        const payload = {
            carData,
            listTotal,
            ebayBatchMeta,
            lastDataMode,
            filters: collectFilterSnapshot(),
            scrollY: window.scrollY,
            savedAt: Date.now(),
        };
        sessionStorage.setItem(INVENTORY_SESSION_KEY, JSON.stringify(payload));
    } catch (err) {
        console.warn('Failed to save inventory session', err);
    }
}

function clearInventorySession() {
    try {
        sessionStorage.removeItem(INVENTORY_SESSION_KEY);
    } catch (_) {
        /* ignore */
    }
}

function restoreInventorySession() {
    try {
        const raw = sessionStorage.getItem(INVENTORY_SESSION_KEY);
        if (!raw) return false;
        const payload = JSON.parse(raw);
        if (!payload?.savedAt || Date.now() - payload.savedAt > INVENTORY_SESSION_TTL_MS) {
            clearInventorySession();
            return false;
        }
        if (!Array.isArray(payload.carData) || payload.carData.length === 0) {
            clearInventorySession();
            return false;
        }

        carData = payload.carData;
        currentResults = carData;
        listTotal = typeof payload.listTotal === 'number' ? payload.listTotal : carData.length;
        ebayBatchMeta = payload.ebayBatchMeta ?? null;
        lastDataMode = payload.lastDataMode ?? 'database';

        applyFilterSnapshot(payload.filters);
        updateUI(currentResults);
        updateResultsHintAndLoadMore();

        const list = document.getElementById('inventoryList');
        list?.removeAttribute('aria-busy');
        list && (list.style.opacity = '');

        if (typeof payload.scrollY === 'number') {
            requestAnimationFrame(() => window.scrollTo(0, payload.scrollY));
        }
        return true;
    } catch (err) {
        console.warn('Failed to restore inventory session', err);
        clearInventorySession();
        return false;
    }
}

function updateResultsHintAndLoadMore() {
    const hint = document.getElementById('inventoryResultsHint');
    const wrap = document.getElementById('inventoryLoadMoreWrap');
    const btn = document.getElementById('loadMoreBtn');
    const dbSuffix = lastDataMode === 'database' ? ' (Database mode)' : '';
    const pendingBatch = ebayBatchMeta?.pending_in_batch ?? 0;
    if (hint) {
        if (listTotal === 0 && carData.length === 0) {
            hint.textContent = 'No listings match your filters.';
        } else if (pendingBatch > 0) {
            hint.textContent = `Showing ${carData.length} listing${carData.length === 1 ? '' : 's'} · ${pendingBatch} more ready from eBay${dbSuffix}`;
        } else if (carData.length >= listTotal) {
            hint.textContent = `Showing all ${listTotal} listing${listTotal === 1 ? '' : 's'}${dbSuffix}`;
        } else {
            hint.textContent = `Showing ${carData.length} of ${listTotal} listings${dbSuffix}`;
        }
    }
    if (wrap && btn) {
        const hasDbMore = listTotal > 0 && carData.length < listTotal;
        const hasEbayMore = loadMoreUsesEbayBatch();
        const hasMore = hasDbMore || hasEbayMore;
        wrap.hidden = !hasMore;
        btn.disabled = !hasMore;
        if (!btn.dataset.loading) {
            btn.textContent = pendingBatch > 0 ? 'Load more from eBay' : 'Load more';
        }
    }
}

async function executeSearch({ append = false, syncEbay = false, scrollToTop } = {}) {
    const list = document.getElementById('inventoryList');
    const hint = document.getElementById('inventoryResultsHint');
    const loadBtn = document.getElementById('loadMoreBtn');
    const q = document.getElementById('globalSearchInput')?.value.trim() || '';
    const effectiveSyncEbay = !append && (syncEbay || !q);
    const useBatchContinue = append && loadMoreUsesEbayBatch();
    const shouldScrollToTop = scrollToTop ?? !append;

    if (!append) {
        clearInventorySession();
        stopAuctionCountdownTimer();
        list.style.opacity = '0.55';
        list.setAttribute('aria-busy', 'true');
        const loadingLabel = effectiveSyncEbay
            ? 'Updating from eBay…'
            : useBatchContinue
              ? 'Loading more from eBay…'
              : 'Loading inventory…';
        const spinner = '<span class="loading-spinner" aria-hidden="true"></span>';
        list.innerHTML = `<div class="loading loading--sync">${spinner}<span>${loadingLabel}</span></div>`;
    } else if (loadBtn) {
        loadBtn.dataset.loading = '1';
        loadBtn.disabled = true;
        loadBtn.textContent = 'Loading…';
    }

    const query = new URL('/api/cars', window.location.origin);
    if (q) query.searchParams.set('q', q);
    if (effectiveSyncEbay) {
        query.searchParams.set('sync_ebay', 'true');
    } else if (useBatchContinue) {
        query.searchParams.set('ebay_batch_continue', 'true');
    }

    appendMultiParams(query, 'countries', Array.from(locSelection.countries));
    appendMultiParams(query, 'regions', Array.from(locSelection.regions));
    Array.from(locSelection.cities).forEach((key) => {
        if (key === LOCATION_NOT_SPECIFIED) {
            query.searchParams.append('cities', LOCATION_NOT_SPECIFIED);
            return;
        }
        const parts = key.split('|');
        if (parts.length === 3) query.searchParams.append('cities', parts[2]);
    });
    appendMultiParams(query, 'makes', Array.from(makeSelection));
    appendMultiParams(query, 'vehicle_titles', getSelectedChipValues('filterVehicleTitles'));

    const radiusWrap = document.getElementById('radiusFilterWrap');
    const radiusMi = Number(document.getElementById('filterRadiusMi')?.value || 0);
    if (
        radiusWrap &&
        !radiusWrap.classList.contains('is-disabled') &&
        radiusWrap.dataset.anchorLat &&
        radiusMi > 0
    ) {
        query.searchParams.set('radius_mi', String(radiusMi));
        query.searchParams.set('anchor_lat', radiusWrap.dataset.anchorLat);
        query.searchParams.set('anchor_lng', radiusWrap.dataset.anchorLng);
    }

    const pmin = Number(document.getElementById('filterPriceMin')?.value);
    const pmax = Number(document.getElementById('filterPriceMax')?.value);
    const priceBounds = priceRangeBounds();
    if (priceBounds.active) {
        if (pmin > priceBounds.lo) query.searchParams.set('min_price', String(pmin));
        if (pmax < priceBounds.hi) query.searchParams.set('max_price', String(pmax));
    }

    const ymin = Number(document.getElementById('filterYearMin')?.value);
    const ymax = Number(document.getElementById('filterYearMax')?.value);
    const yearBounds = yearRangeBounds();
    if (yearBounds.active) {
        if (ymin > yearBounds.lo) query.searchParams.set('min_year', String(ymin));
        if (ymax < yearBounds.hi) query.searchParams.set('max_year', String(ymax));
    }

    const mmin = Number(document.getElementById('filterMileageMin')?.value);
    const mmax = Number(document.getElementById('filterMileageMax')?.value);
    const mileageBounds = mileageRangeBounds();
    if (mileageBounds.active) {
        if (mmin > mileageBounds.lo) query.searchParams.set('min_mileage', String(Math.round(mmin)));
        if (mmax < mileageBounds.hi) query.searchParams.set('max_mileage', String(Math.round(mmax)));
    }

    appendMultiParams(query, 'body_styles', getSelectedChipValues('filterBodyTypes'));
    appendMultiParams(query, 'delivery_modes', getSelectedChipValues('filterDelivery'));
    appendMultiParams(query, 'conditions', getSelectedChipValues('filterConditions'));
    appendMultiParams(query, 'listing_formats', getSelectedChipValues('filterListingFormats'));

    const minRoi = document.getElementById('filterMinRoi')?.value.trim();
    const minProfit = document.getElementById('filterMinProfit')?.value.trim();
    if (minRoi) query.searchParams.set('min_roi', minRoi);
    if (minProfit) query.searchParams.set('min_profit', minProfit);
    if (document.getElementById('filterExcludeNegativeProfit')?.checked) {
        query.searchParams.set('exclude_negative_profit', 'true');
    }
    if (document.getElementById('filterExcludeEndedAuctions')?.checked !== false) {
        query.searchParams.set('exclude_ended_auctions', 'true');
    } else {
        query.searchParams.set('exclude_ended_auctions', 'false');
    }
    if (document.getElementById('filterExcludeUnknownPrice')?.checked) {
        query.searchParams.set('exclude_unknown_price', 'true');
    }

    const sortBy = document.getElementById('frontendSortBy')?.value || 'roi';
    query.searchParams.set('sort_by', sortBy);
    query.searchParams.set('sort_order', sortDesc ? 'desc' : 'asc');
    query.searchParams.set('limit', String(PAGE_SIZE));
    query.searchParams.set('offset', String(append ? carData.length : 0));

    try {
        let response = await fetch(query, { credentials: 'include' });
        if (response.status === 401) {
            window.location.replace('login.html');
            return;
        }
        if (response.status === 429) {
            let msg = 'eBay sync is on cooldown; showing saved listings.';
            try {
                const errBody = await response.json();
                const sec = errBody?.detail?.retry_after_sec;
                if (typeof sec === 'number') {
                    msg = `eBay sync cooldown (${Math.ceil(sec)}s); showing saved listings.`;
                }
            } catch (_) {
                /* ignore */
            }
            showEbayToast(msg, { variant: 'warn' });
            if (hint) hint.textContent = msg;
            const fallbackUrl = new URL(query);
            fallbackUrl.searchParams.delete('sync_ebay');
            response = await fetch(fallbackUrl, { credentials: 'include' });
        }
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = await response.json();
        const items = Array.isArray(payload.items) ? payload.items : [];
        listTotal = typeof payload.total === 'number' ? payload.total : items.length;
        lastDataMode = payload.data_mode === 'ebay_refreshed' ? 'ebay_refreshed' : 'database';
        ebayBatchMeta = resolveEbayBatchMeta(payload);

        if (payload.ebay_sync?.status === 'failed') {
            const errMsg =
                payload.ebay_sync.error ||
                'eBay sync failed; showing saved listings.';
            showEbayToast(String(errMsg), { variant: 'error' });
            if (hint && !hint.textContent.includes('cooldown')) {
                hint.textContent = 'eBay sync failed; showing saved listings.';
            }
        }

        if (append) {
            carData = carData.concat(items);
        } else {
            carData = items;
        }
        currentResults = carData;
        updateUI(currentResults);
        updateResultsHintAndLoadMore();
        saveInventorySession();
        if (!append && shouldScrollToTop) {
            requestAnimationFrame(() => scrollInventoryToTop());
        }
        list.removeAttribute('aria-busy');
    } catch (err) {
        console.error('Search failed:', err);
        if (effectiveSyncEbay || useBatchContinue) {
            showEbayToast('Unable to reach eBay or the server. Showing saved listings if available.', {
                variant: 'error',
            });
        }
        let recovered = false;
        if (!append) {
            const fallbackUrl = new URL(query);
            if (fallbackUrl.searchParams.has('sync_ebay')) {
                fallbackUrl.searchParams.delete('sync_ebay');
                try {
                    const fbRes = await fetch(fallbackUrl, { credentials: 'include' });
                    if (fbRes.status === 401) {
                        window.location.replace('login.html');
                        return;
                    }
                    if (fbRes.ok) {
                        const payload = await fbRes.json();
                        const items = Array.isArray(payload.items) ? payload.items : [];
                        listTotal = typeof payload.total === 'number' ? payload.total : items.length;
                        lastDataMode = 'database';
                        carData = items;
                        currentResults = carData;
                        updateUI(currentResults);
                        updateResultsHintAndLoadMore();
                        if (hint) {
                            hint.textContent =
                                'Connection issue during eBay sync; showing saved listings (Database mode).';
                        }
                        recovered = true;
                    }
                } catch (fbErr) {
                    console.error('DB fallback after connection error failed:', fbErr);
                }
            }
            if (!recovered && carData.length > 0) {
                lastDataMode = 'database';
                updateUI(carData);
                updateResultsHintAndLoadMore();
                if (hint) {
                    hint.textContent = 'Unable to refresh; showing last loaded listings (Database mode).';
                }
                recovered = true;
            }
            if (!recovered) {
                list.innerHTML =
                    '<div class="no-results"><div>Connection error</div><div style="margin-top:8px;font-size:13px;">Unable to reach the server.</div></div>';
                if (hint) hint.textContent = '';
            }
        }
    } finally {
        list.style.opacity = '1';
        list.removeAttribute('aria-busy');
        if (loadBtn) {
            delete loadBtn.dataset.loading;
            loadBtn.textContent = 'Load more';
            loadBtn.disabled = false;
            updateResultsHintAndLoadMore();
        }
    }
}

function attrEncode(s) {
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/**
 * Dot strip modes (always up to 7 visible dots when count > 7):
 * - edge-start / edge-end: fixed window of 7 dots; only the pointer moves
 * - slide: starts when the pointer reaches the 4th dot (center of 7), then window slides with photos
 * - short: count ≤ 7 — all dots, pointer only
 */
function carouselDotWindow(count, activeIndex) {
    if (count <= MAX_CAROUSEL_DOTS) {
        return { start: 0, end: count - 1, mode: 'short' };
    }

    const lastSlideCenter = count - 1 - CAROUSEL_DOTS_CENTER_IDX;

    if (activeIndex < CAROUSEL_DOTS_CENTER_IDX) {
        return { start: 0, end: MAX_CAROUSEL_DOTS - 1, mode: 'edge-start' };
    }
    if (activeIndex > lastSlideCenter) {
        return {
            start: count - MAX_CAROUSEL_DOTS,
            end: count - 1,
            mode: 'edge-end',
        };
    }
    return {
        start: activeIndex - CAROUSEL_DOTS_CENTER_IDX,
        end: activeIndex + CAROUSEL_DOTS_CENTER_IDX,
        mode: 'slide',
    };
}

function applyCarouselDotsMode(dotsRoot, mode) {
    if (!dotsRoot) return;
    const slide = mode === 'slide';
    dotsRoot.classList.toggle('is-carousel-slide', slide);
    dotsRoot.classList.toggle('is-carousel-edge', !slide);
}

function carouselDotsButtonsHtml(count, activeIndex) {
    const win = carouselDotWindow(count, activeIndex);
    let buttons = '';
    for (let slideIdx = win.start; slideIdx <= win.end; slideIdx += 1) {
        const edge =
            count > MAX_CAROUSEL_DOTS &&
            ((slideIdx === win.start && win.start > 0) || (slideIdx === win.end && win.end < count - 1));
        const edgeCls = edge ? ' is-window-edge' : '';
        buttons += `<button type="button" class="car-card-carousel-dot${edgeCls}" data-slide-to="${slideIdx}" aria-label="Photo ${slideIdx + 1}" aria-current="${slideIdx === activeIndex ? 'true' : 'false'}"></button>`;
    }
    return buttons;
}

function carouselDotsMarkup(count, activeIndex) {
    if (count < 2) return '';
    return `<div class="car-card-carousel-dots"><div class="car-card-carousel-dots-viewport"><span class="car-card-carousel-dots-center" aria-hidden="true"></span><div class="car-card-carousel-dots-track">${carouselDotsButtonsHtml(count, activeIndex)}</div></div></div>`;
}

function carouselDotStepPx(track) {
    const first = track?.querySelector('.car-card-carousel-dot');
    if (!first) return 12;
    const second = first.nextElementSibling;
    if (second) return Math.max(8, second.offsetLeft - first.offsetLeft);
    const gap = parseFloat(getComputedStyle(track).gap) || 6;
    return first.offsetWidth + gap;
}

function refreshCarouselDots(dotsRoot, count, activeIndex, direction) {
    if (!dotsRoot) return;
    const track = dotsRoot.querySelector('.car-card-carousel-dots-track');
    if (!track) return;
    const win = carouselDotWindow(count, activeIndex);
    applyCarouselDotsMode(dotsRoot, win.mode);
    const winKey = `${win.mode}:${win.start}-${win.end}`;
    if (track.dataset.winKey === winKey) {
        track.querySelectorAll('.car-card-carousel-dot').forEach((btn) => {
            const idx = Number(btn.dataset.slideTo);
            btn.setAttribute('aria-current', idx === activeIndex ? 'true' : 'false');
        });
        track.style.transform = 'translateX(0)';
        return;
    }
    const prevStart = Number(track.dataset.winStart ?? win.start);
    const prevKey = track.dataset.winKey || '';
    const slideDelta = win.start - prevStart;
    track.dataset.winKey = winKey;
    track.dataset.winStart = String(win.start);
    track.innerHTML = carouselDotsButtonsHtml(count, activeIndex);

    const shouldAnimateStrip =
        win.mode === 'slide' &&
        prevKey.startsWith('slide:') &&
        prevKey !== winKey &&
        slideDelta !== 0;

    if (shouldAnimateStrip) {
        const step = carouselDotStepPx(track);
        const goingNext =
            direction === 'next' || (direction == null && slideDelta > 0);
        track.style.transition = 'none';
        track.style.transform = goingNext
            ? `translateX(${step}px)`
            : `translateX(${-step}px)`;
        requestAnimationFrame(() => {
            track.style.transition = 'transform 0.28s ease';
            track.style.transform = 'translateX(0)';
        });
    } else {
        track.style.transition = '';
        track.style.transform = 'translateX(0)';
    }
}

function carouselHtml(car) {
    const imgs = car.images && car.images.length ? car.images : car.image_url ? [car.image_url] : [];
    if (!imgs.length) {
        return `
            <div class="car-card-carousel">
                <div class="car-card-carousel-placeholder">No photo</div>
            </div>`;
    }
    const slides = imgs
        .map(
            (url, i) =>
                `<img class="car-card-carousel-img" src="${attrEncode(url)}" alt="" data-slide="${i}" loading="lazy" draggable="false">`
        )
        .join('');
    const nav =
        imgs.length > 1
            ? `
        <button type="button" class="car-card-carousel-nav car-card-carousel-nav--prev" aria-label="Previous photo">
            <svg class="car-card-carousel-nav-svg" width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7"/></svg>
        </button>
        <button type="button" class="car-card-carousel-nav car-card-carousel-nav--next" aria-label="Next photo">
            <svg class="car-card-carousel-nav-svg" width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"/></svg>
        </button>
        ${carouselDotsMarkup(imgs.length, 0)}`
            : '';
    const strip =
        imgs.length > 1
            ? `<div class="car-card-carousel-viewport"><div class="car-card-carousel-strip">${slides}</div></div>`
            : `<img class="car-card-carousel-img" src="${attrEncode(imgs[0])}" alt="" loading="lazy" draggable="false">`;
    return `<div class="car-card-carousel" data-carousel data-count="${imgs.length}">${strip}${nav}</div>`;
}

function locationLine(car) {
    const L = car.location;
    if (!L) return 'Location: —';
    const parts = [L.city, L.region];
    if (locSelection.countries.size !== 1 && L.country) {
        parts.push(L.country);
    }
    const filtered = parts.filter(Boolean);
    return filtered.length ? `Location: ${filtered.join(', ')}` : 'Location: —';
}

function listingLinkLabel(car) {
    const src = (car.source || '').toLowerCase();
    if (src === 'ebay') return 'View on eBay';
    if (src === 'demo') return 'View listing';
    return 'View listing';
}

function getListingUrl(car) {
    const direct = (car.listing_url || '').trim();
    if (direct.startsWith('http://') || direct.startsWith('https://')) {
        return direct;
    }
    const ext = (car.external_listing_id || '').trim();
    if (!ext) return '';
    const parts = ext.split('|');
    let numeric = '';
    if (parts.length >= 2 && /^\d+$/.test(parts[1])) {
        numeric = parts[1];
    } else if (/^\d+$/.test(ext)) {
        numeric = ext;
    }
    return numeric ? `https://www.ebay.com/itm/${numeric}` : '';
}

function listingLinkHtml(car, className = 'car-card-listing-link') {
    const url = getListingUrl(car);
    if (!url) return '';
    return `<a class="${className}" href="${attrEncode(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(listingLinkLabel(car))}</a>`;
}

function priceRangeBounds() {
    if (!inventoryMeta || inventoryMeta.max_price <= inventoryMeta.min_price) {
        return { lo: 0, hi: 0, active: false };
    }
    const lo = Math.floor(inventoryMeta.min_price / 100) * 100;
    const hi = Math.ceil(inventoryMeta.max_price / 100) * 100;
    return { lo, hi, active: true };
}

function yearRangeBounds() {
    if (!inventoryMeta || inventoryMeta.max_year <= inventoryMeta.min_year) {
        return { lo: 0, hi: 0, active: false };
    }
    return { lo: inventoryMeta.min_year, hi: inventoryMeta.max_year, active: true };
}

function mileageRangeBounds() {
    if (
        !inventoryMeta ||
        inventoryMeta.min_mileage == null ||
        inventoryMeta.max_mileage == null ||
        inventoryMeta.max_mileage <= inventoryMeta.min_mileage
    ) {
        return { lo: 0, hi: 0, active: false };
    }
    const step = 500;
    return {
        lo: Math.floor(Number(inventoryMeta.min_mileage) / step) * step,
        hi: Math.ceil(Number(inventoryMeta.max_mileage) / step) * step,
        active: true,
    };
}

function specLines(car) {
    const body = car.body_style || '—';
    const drive = car.drive_type || '—';
    const title = car.vehicle_title || '—';
    const mech = [car.transmission, car.engine].filter(Boolean).join(' · ');
    const mechLine = mech
        ? `<span class="car-card-spec-line">${escapeHtml(mech)}</span>`
        : '';
    return `
        <span class="car-card-spec-line">${escapeHtml(locationLine(car))}</span>
        <span class="car-card-spec-line">${escapeHtml(body)} · ${escapeHtml(drive)}</span>
        <span class="car-card-spec-line">Title: ${escapeHtml(title)}</span>
        ${mechLine}
        <span class="car-card-spec-line">${escapeHtml(deliverySummary(car.delivery))}</span>
    `;
}

function modalVehicleDetailsHtml(car) {
    const fuelMpg =
        car.fuel_city != null && car.fuel_highway != null
            ? `${car.fuel_city} / ${car.fuel_highway} mpg`
            : null;
    const rows = [
        ['VIN', car.vin],
        ['Trim', car.trim],
        ['Engine', car.engine],
        ['Transmission', car.transmission],
        ['Fuel type', car.fuel_type],
        ['Fuel (city / hwy)', fuelMpg],
    ].filter(([, value]) => value != null && String(value).trim() !== '');
    if (rows.length === 0) return '';
    const items = rows
        .map(
            ([label, value]) =>
                `<div class="modal-vehicle-detail-row"><span class="modal-vehicle-detail-label">${escapeHtml(label)}</span><span class="modal-vehicle-detail-value">${escapeHtml(String(value))}</span></div>`,
        )
        .join('');
    return `<div class="modal-vehicle-details"><div class="modal-vehicle-details-title">Vehicle details</div>${items}</div>`;
}

function updateUI(items) {
    const list = document.getElementById('inventoryList');
    const L = window.Css360Listing;
    if (items.length === 0) {
        stopAuctionCountdownTimer();
        list.innerHTML = '<div class="no-results"><div>No matches. Try widening filters or search.</div></div>';
        return;
    }

    list.innerHTML = items
        .map((car) =>
            L.buildCarCardHtml(car, {
                showWatchButton: true,
                isWatched: watchlistIds.has(car.id),
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
            const car = items.find((c) => parseCarId(c.id) === carId);
            if (car) openListingDetail(car);
        });
    });

    list.querySelectorAll('.car-card-watch-btn').forEach((btn) => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const carId = Number(btn.dataset.carId);
            if (carId) toggleWatchlistCar(carId, btn);
        });
    });

    L.initCarouselsIn(list);
    ensureAuctionCountdownTimer();
}

async function fetchWatchlistIds() {
    try {
        const res = await fetch('/api/watchlist/ids', { credentials: 'include' });
        if (!res.ok) return;
        const data = await res.json();
        watchlistIds = new Set(data.ids || []);
    } catch (_) {
        /* ignore */
    }
}

function openListingDetail(car) {
    const carId = parseCarId(car?.id);
    if (!carId) return;
    const mode = getSettings().listingDetailMode;
    if (mode === 'page') {
        const returnUrl = `${window.location.pathname}${window.location.search}`;
        window.location.href = `/car.html?id=${carId}&return=${encodeURIComponent(returnUrl)}`;
        return;
    }
    showCarDetails(car);
}

async function toggleWatchlistCar(carId, btn) {
    const isWatched = watchlistIds.has(carId);
    try {
        const res = await fetch(`/api/watchlist/${carId}`, {
            method: isWatched ? 'DELETE' : 'POST',
            credentials: 'include',
        });
        if (res.status === 409) {
            showEbayToast(
                'You can track at most 10 listings. Remove one from Profile first.',
                { variant: 'warn' },
            );
            return;
        }
        if (!res.ok) return;
        if (isWatched) watchlistIds.delete(carId);
        else watchlistIds.add(carId);
        const next = !isWatched;
        btn.classList.toggle('is-watched', next);
        btn.setAttribute('aria-pressed', next ? 'true' : 'false');
        btn.setAttribute('aria-label', next ? 'Remove from watchlist' : 'Add to watchlist');
    } catch (err) {
        console.error(err);
    }
}

function showCarDetails(car) {
    const modal = document.getElementById('itemModal');
    const header = document.getElementById('modalHeader');
    const content = document.getElementById('modalContent');

    header.textContent =
        car.year != null ? `${car.brand} ${car.model} (${car.year})` : `${car.brand} ${car.model}`;

    const mileageDisplay =
        car.mileage != null ? `${Number(car.mileage).toLocaleString()} mi` : 'Unknown mileage';
    const modalSettings = getSettings();
    const isEbayListing =
        (car.source || '').toLowerCase() === 'ebay' && Boolean(car.external_listing_id);
    const ebayRefreshBtn = isEbayListing
        ? '<button type="button" class="modal-refresh-btn" id="modalRefreshEbayBtn">Refresh from eBay</button>'
        : '';
    const deleteCarBtn = modalSettings.showDeleteCarButton
        ? '<button type="button" class="modal-delete-btn" id="modalDeleteCarBtn">Delete from database</button>'
        : '';
    const jsonDebugBtn = modalSettings.showListingJsonDebug
        ? '<button type="button" class="modal-json-debug-btn" id="modalViewRawJsonBtn">View raw JSON</button>'
        : '';
    const econKnown = isPriceKnown(car);
    const resaleDisplay = econKnown ? `$${Number(car.resale_value).toLocaleString()}` : '—';
    const repairDisplay = econKnown ? `$${Number(car.repair_cost).toLocaleString()}` : '—';
    const metricsSection = shouldShowEconomics(car)
        ? `<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
                <div style="background:var(--bg-page);padding:12px;border-radius:8px;">
                    <div style="color:var(--text-muted);font-size:12px;margin-bottom:4px;">EST. NET PROFIT</div>
                    <div style="font-size:24px;font-weight:700;color:${car.net_profit >= 0 ? 'var(--accent-green)' : '#ef4444'};">${escapeHtml(formatProfitDisplay(car))}</div>
                </div>
                <div style="background:var(--bg-page);padding:12px;border-radius:8px;">
                    <div style="color:var(--text-muted);font-size:12px;margin-bottom:4px;">ROI</div>
                    <div style="font-size:24px;font-weight:700;color:${car.roi >= 0 ? 'var(--accent-green)' : '#ef4444'};">${escapeHtml(formatRoiDisplay(car))}</div>
                </div>
            </div>`
        : '';

    content.innerHTML = `
        <div style="display:flex;flex-direction:column;gap:16px;">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
                <div><div style="color:var(--text-muted);font-size:12px;margin-bottom:4px;">PURCHASE</div>
                    <div style="font-size:20px;font-weight:700;">${modalPurchasePriceHtml(car)}</div></div>
                <div><div style="color:var(--text-muted);font-size:12px;margin-bottom:4px;">RESALE</div>
                    <div style="font-size:20px;font-weight:700;">${resaleDisplay}</div></div>
                <div><div style="color:var(--text-muted);font-size:12px;margin-bottom:4px;">REPAIR</div>
                    <div style="font-size:20px;font-weight:700;">${repairDisplay}</div></div>
                <div><div style="color:var(--text-muted);font-size:12px;margin-bottom:4px;">MILEAGE</div>
                    <div style="font-size:20px;font-weight:700;">${escapeHtml(mileageDisplay)}</div></div>
            </div>
            <div style="height:1px;background:var(--separator);"></div>
            ${metricsSection}
            ${modalVehicleDetailsHtml(car)}
            ${listingLinkHtml(car, 'modal-listing-link')}
            ${ebayRefreshBtn}
            ${deleteCarBtn}
            ${jsonDebugBtn}
            <pre class="modal-raw-json" id="modalRawJsonPre" hidden></pre>
        </div>`;

    document.getElementById('modalRefreshEbayBtn')?.addEventListener('click', async () => {
        const btn = document.getElementById('modalRefreshEbayBtn');
        if (!btn) return;
        btn.disabled = true;
        btn.textContent = 'Refreshing…';
        try {
            const res = await fetch(`/api/cars/${car.id}/ebay-refresh`, {
                method: 'POST',
                credentials: 'include',
            });
            if (res.status === 401) {
                window.location.replace('login.html');
                return;
            }
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            if (data.deleted) {
                carData = carData.filter((c) => c.id !== car.id);
                currentResults = carData;
                listTotal = Math.max(0, listTotal - 1);
                updateUI(currentResults);
                updateResultsHintAndLoadMore();
                saveInventorySession();
                hideModal();
                showEbayToast(
                    data.message ||
                        'This listing is no longer available on eBay and was removed from your inventory.',
                    { variant: 'warn' }
                );
                return;
            }
            const updated = data.item;
            if (!updated) throw new Error('missing item');
            const idx = carData.findIndex((c) => c.id === car.id);
            if (idx >= 0) carData[idx] = updated;
            currentResults = carData;
            updateUI(currentResults);
            showCarDetails(updated);
            saveInventorySession();
        } catch (err) {
            console.error(err);
            showEbayToast('Failed to refresh this listing from eBay. Please try again.', {
                variant: 'error',
            });
            btn.disabled = false;
            btn.textContent = 'Refresh from eBay';
        }
    });

    document.getElementById('modalDeleteCarBtn')?.addEventListener('click', async () => {
        const btn = document.getElementById('modalDeleteCarBtn');
        if (!btn) return;
        const title =
            car.year != null ? `${car.brand} ${car.model} (${car.year})` : `${car.brand} ${car.model}`;
        const ok = await showConfirmDialog({
            title: 'Delete listing?',
            message: `Permanently delete "${title}" from the database? This cannot be undone.`,
            confirmText: 'Delete',
            cancelText: 'Cancel',
        });
        if (!ok) return;
        btn.disabled = true;
        btn.textContent = 'Deleting…';
        try {
            const res = await fetch(`/api/cars/${car.id}`, {
                method: 'DELETE',
                credentials: 'include',
            });
            if (res.status === 401) {
                window.location.replace('login.html');
                return;
            }
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            hideModal();
            carData = carData.filter((c) => c.id !== car.id);
            currentResults = carData;
            listTotal = Math.max(0, listTotal - 1);
            updateUI(currentResults);
            updateResultsHintAndLoadMore();
        } catch (err) {
            console.error(err);
            showEbayToast('Failed to delete this listing. Please try again.', { variant: 'error' });
            btn.disabled = false;
            btn.textContent = 'Delete from database';
        }
    });

    document.getElementById('modalViewRawJsonBtn')?.addEventListener('click', async () => {
        const pre = document.getElementById('modalRawJsonPre');
        const btn = document.getElementById('modalViewRawJsonBtn');
        if (!pre || !btn) return;
        if (!pre.hidden && pre.textContent) {
            pre.hidden = true;
            btn.textContent = 'View raw JSON';
            return;
        }
        btn.disabled = true;
        btn.textContent = 'Loading…';
        try {
            const res = await fetch(`/api/cars/${car.id}/raw-listing`, { credentials: 'include' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            pre.textContent = JSON.stringify(data.raw_listing_json, null, 2);
            pre.hidden = false;
            btn.textContent = 'Hide raw JSON';
        } catch (err) {
            console.error(err);
            pre.textContent = 'Failed to load raw listing JSON.';
            pre.hidden = false;
            btn.textContent = 'View raw JSON';
        } finally {
            btn.disabled = false;
        }
    });

    modal.classList.add('active');
}

function hideModal() {
    document.getElementById('itemModal').classList.remove('active');
}

/**
 * @param {{ title: string, message: string, confirmText?: string, cancelText?: string }} opts
 * @returns {Promise<boolean>}
 */
function showConfirmDialog(opts) {
    const modal = document.getElementById('confirmModal');
    const titleEl = document.getElementById('confirmModalTitle');
    const messageEl = document.getElementById('confirmModalMessage');
    const cancelBtn = document.getElementById('confirmModalCancelBtn');
    const confirmBtn = document.getElementById('confirmModalConfirmBtn');
    if (!modal || !titleEl || !messageEl || !cancelBtn || !confirmBtn) {
        return Promise.resolve(false);
    }

    titleEl.textContent = opts.title;
    messageEl.textContent = opts.message;
    cancelBtn.textContent = opts.cancelText || 'Cancel';
    confirmBtn.textContent = opts.confirmText || 'Confirm';

    return new Promise((resolve) => {
        let settled = false;
        const finish = (value) => {
            if (settled) return;
            settled = true;
            modal.classList.remove('active');
            modal.hidden = true;
            document.removeEventListener('keydown', onKeydown);
            cancelBtn.removeEventListener('click', onCancel);
            confirmBtn.removeEventListener('click', onConfirm);
            modal.removeEventListener('click', onBackdrop);
            resolve(value);
        };
        const onCancel = () => finish(false);
        const onConfirm = () => finish(true);
        const onBackdrop = (e) => {
            if (e.target === modal) finish(false);
        };
        const onKeydown = (e) => {
            if (e.key === 'Escape') finish(false);
        };

        cancelBtn.addEventListener('click', onCancel);
        confirmBtn.addEventListener('click', onConfirm);
        modal.addEventListener('click', onBackdrop);
        document.addEventListener('keydown', onKeydown);

        modal.hidden = false;
        modal.classList.add('active');
        cancelBtn.focus();
    });
}

function resetFilters() {
    document.querySelectorAll('.filter-chip').forEach((b) => b.setAttribute('aria-pressed', 'false'));
    document.getElementById('filterMinRoi').value = '';
    document.getElementById('filterMinProfit').value = '';
    const excludeProfit = document.getElementById('filterExcludeNegativeProfit');
    if (excludeProfit) excludeProfit.checked = false;
    const excludeEnded = document.getElementById('filterExcludeEndedAuctions');
    if (excludeEnded) excludeEnded.checked = true;
    const excludeUnknownPrice = document.getElementById('filterExcludeUnknownPrice');
    if (excludeUnknownPrice) excludeUnknownPrice.checked = false;
    makeSelection.clear();
    clearLocationSelections();
    if (inventoryMeta) populateMetaIntoUi(inventoryMeta);
    refreshRegionOptions();
    refreshCityOptions();
    updateRadiusAvailability();
    updateMakeTriggerLabel();
    const rlab = document.getElementById('filterRadiusMiLabel');
    const rIn = document.getElementById('filterRadiusMi');
    if (rIn && rlab) rlab.textContent = rIn.value;
    executeSearch({ append: false });
}

function initFilterToggles() {
    document.querySelectorAll('.filter-toggle').forEach((label) => {
        const input = label.querySelector('input[type="checkbox"]');
        if (!input) return;
        input.tabIndex = -1;
        // Prevent focus scroll when clicking custom toggle switches in the sidebar.
        label.addEventListener('mousedown', (e) => {
            e.preventDefault();
        });
    });
}

function initEventListeners() {
    initFilterToggles();
    document
        .getElementById('applyFiltersBtn')
        ?.addEventListener('click', () => executeSearch({ append: false, syncEbay: false }));
    document.getElementById('resetFiltersBtn')?.addEventListener('click', resetFilters);
    document.getElementById('loadMoreBtn')?.addEventListener('click', () => executeSearch({ append: true }));
    document.getElementById('viewListBtn')?.addEventListener('click', () => setViewMode('list'));
    document.getElementById('viewGridBtn')?.addEventListener('click', () => setViewMode('grid'));
    document.getElementById('frontendSortBy')?.addEventListener('change', () => executeSearch({ append: false }));
    document.getElementById('sortOrderToggle')?.addEventListener('click', toggleSortOrder);
    document.getElementById('closeModalBtn')?.addEventListener('click', hideModal);
    document.getElementById('itemModal')?.addEventListener('click', (e) => {
        if (e.target === e.currentTarget) hideModal();
    });
    document
        .getElementById('globalSearchBtn')
        ?.addEventListener('click', () => executeSearch({ append: false, syncEbay: true }));
    document.getElementById('globalSearchInput')?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            executeSearch({ append: false, syncEbay: true });
        }
    });

    document.getElementById('filterRadiusMi')?.addEventListener('input', (e) => {
        const lab = document.getElementById('filterRadiusMiLabel');
        if (lab) lab.textContent = e.target.value;
    });

    document.querySelector('a.app-account-menu-item[href="settings.html"]')?.addEventListener('click', () => {
        saveInventorySession();
    });

    window.addEventListener('pagehide', () => {
        saveInventorySession();
    });
}

function reapplySavedFilterSnapshot() {
    try {
        const raw = sessionStorage.getItem(INVENTORY_SESSION_KEY);
        if (!raw) return;
        const payload = JSON.parse(raw);
        if (payload?.filters) applyFilterSnapshot(payload.filters);
    } catch (_) {
        /* ignore */
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    initAppShell();
    const me = await requireAuth();
    if (!me) return;

    setNotificationsBadge(me.notifications_unread_count);
    await fetchWatchlistIds();
    void runWatchCheckIfDue();

    initViewMode();
    initSortOrderUi();
    initFilterDropdowns();
    initEventListeners();

    wireDualRange('price', document.getElementById('filterPriceMin'), document.getElementById('filterPriceMax'));
    wireDualRange('year', document.getElementById('filterYearMin'), document.getElementById('filterYearMax'));
    wireDualRange('mileage', document.getElementById('filterMileageMin'), document.getElementById('filterMileageMax'));

    const restored = restoreInventorySession();

    let meta = await fetchMeta();
    if (meta) populateMetaIntoUi(meta, !restored);
    if (restored) reapplySavedFilterSnapshot();

    if (restored) {
        const metaFresh = await fetchMeta();
        if (metaFresh) {
            populateMetaIntoUi(metaFresh, false);
            reapplySavedFilterSnapshot();
        }
        refreshRegionOptions();
        refreshCityOptions();
        updateRadiusAvailability();
        updateLocationTierUi();
        updateMakeTriggerLabel();
        return;
    }

    refreshRegionOptions();
    refreshCityOptions();
    updateRadiusAvailability();
    updateLocationTierUi();

    await executeSearch({ append: false, syncEbay: true });
    const metaAfterSync = (await fetchMeta()) || meta;
    if (metaAfterSync) {
        populateMetaIntoUi(metaAfterSync, false);
        refreshRegionOptions();
        refreshCityOptions();
        updateRadiusAvailability();
        updateLocationTierUi();
    }
});
