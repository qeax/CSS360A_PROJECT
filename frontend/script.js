/**
 * CSS360 Car Flip Dashboard — inventory UI, filters, global search.
 */

const VIEW_STORAGE_KEY = 'inventory_view';
const SORT_DESC_KEY = 'inventory_sort_desc';
const PAGE_SIZE = 30;
const YEAR_GAP = 1;
const PRICE_GAP = 100;
const MILEAGE_GAP = 500;

let carData = [];
let currentResults = [];
let listTotal = 0;
let inventoryMeta = null;
let sortDesc = true;
let globalSearchTimer = null;

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

function toggleTheme() {
    document.body.classList.toggle('light-theme');
    const isLight = document.body.classList.contains('light-theme');
    localStorage.setItem('theme', isLight ? 'light' : 'dark');
}

function initTheme() {
    if (localStorage.getItem('theme') === 'light') {
        document.body.classList.add('light-theme');
    }
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
function metricsBlockHeatStyle(roi) {
    const heat = calculateHeatmap(roi, 40, 58);
    const border = calculateHeatmapBorder(roi);
    return `background: color-mix(in srgb, ${heat} 22%, var(--bg-page)); border-color: color-mix(in srgb, ${border} 55%, var(--border-color));`;
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

function formatAuctionTimeLeft(iso) {
    if (!iso) return '';
    const end = new Date(iso);
    if (Number.isNaN(end.getTime())) return '';
    const ms = end.getTime() - Date.now();
    if (ms <= 0) return 'Ended';
    const hours = Math.ceil(ms / 3_600_000);
    if (hours < 24) return `${hours}h left`;
    const days = Math.ceil(hours / 24);
    return `${days}d left`;
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
        const left = formatAuctionTimeLeft(car.listing_ends_at);
        const parts = [`${bids} bid${bids === 1 ? '' : 's'}`];
        if (left) parts.push(left);
        return { text: parts.join(' · '), showSep: true };
    }
    return { text: listingFormatLabel(car.listing_format), showSep: true };
}

function carSubtitleLine(car) {
    const cond = car.condition || '—';
    const miles = car.mileage != null ? `${Number(car.mileage).toLocaleString()} mi` : '— mi';
    return `${cond} · ${miles}`;
}

function priceBlockHtml(car) {
    const meta = formatListingMeta(car);
    const sep =
        meta.text && meta.showSep
            ? '<span class="car-card-price-sep" aria-hidden="true">|</span>'
            : '';
    const metaHtml = meta.text
        ? meta.showSep
            ? `<span class="car-card-listing-meta">${escapeHtml(meta.text)}</span>`
            : `<span class="car-card-listing-meta car-card-listing-meta--inline">${escapeHtml(meta.text)}</span>`
        : '';
    return `<div class="car-card-price-block"><span class="car-card-price">$${Number(car.price).toLocaleString()}</span>${sep}${metaHtml}</div>`;
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
    if (n === 1) {
        const v = Array.from(set)[0];
        return v.length > 22 ? `${v.slice(0, 20)}…` : v;
    }
    return `${n} ${kind}${n === 1 ? '' : 's'}`;
}

function summarizeCityButton() {
    const n = locSelection.cities.size;
    if (!n) return 'Any';
    if (n === 1) {
        const k = Array.from(locSelection.cities)[0];
        const parts = k.split('|');
        const name = parts[2] || k;
        return name.length > 22 ? `${name.slice(0, 20)}…` : name;
    }
    return `${n} cities`;
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
        if (!validRegions.has(r)) locSelection.regions.delete(r);
    }
    const validCities = new Set(getAvailableCityRows().map((row) => row.full));
    for (const c of Array.from(locSelection.cities)) {
        if (!validCities.has(c)) locSelection.cities.delete(c);
    }
}

/** When a tier has one option, select it by default; user can still uncheck (onlyIfEmpty avoids re-select after manual clear). */
function applyLocationSingletonDefaults({ tiers = ['country', 'region', 'city'], onlyIfEmpty = true } = {}) {
    if (!inventoryMeta) return false;
    let changed = false;

    if (tiers.includes('country')) {
        const list = inventoryMeta.countries || [];
        if (list.length === 1 && (!onlyIfEmpty || locSelection.countries.size === 0)) {
            locSelection.countries.add(list[0]);
            changed = true;
        }
    }
    if (tiers.includes('region') && locSelection.countries.size > 0) {
        const list = getAvailableRegionsList();
        if (list.length === 1 && (!onlyIfEmpty || locSelection.regions.size === 0)) {
            locSelection.regions.add(list[0]);
            changed = true;
        }
    }
    if (tiers.includes('city') && locSelection.regions.size > 0) {
        const rows = getAvailableCityRows();
        if (rows.length === 1 && (!onlyIfEmpty || locSelection.cities.size === 0)) {
            locSelection.cities.add(rows[0].full);
            changed = true;
        }
    }
    if (changed) {
        updateLocationTriggerLabels();
        updateLocationTierUi();
        updateRadiusAvailability();
    }
    return changed;
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
    const countries = inventoryMeta.countries || [];
    container.innerHTML = countries
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
            applyLocationSingletonDefaults({ tiers: ['region', 'city'], onlyIfEmpty: true });
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
    container.innerHTML = sorted
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
            applyLocationSingletonDefaults({ tiers: ['city'], onlyIfEmpty: true });
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
    container.innerHTML = rows
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

function populateMetaIntoUi(meta) {
    inventoryMeta = meta;
    const pmin = document.getElementById('filterPriceMin');
    const pmax = document.getElementById('filterPriceMax');
    const ymin = document.getElementById('filterYearMin');
    const ymax = document.getElementById('filterYearMax');
    const mmin = document.getElementById('filterMileageMin');
    const mmax = document.getElementById('filterMileageMax');
    if (pmin && pmax) {
        const lo = Math.floor(meta.min_price / 100) * 100;
        const hi = Math.ceil(meta.max_price / 100) * 100;
        [pmin, pmax].forEach((el) => {
            el.min = String(lo);
            el.max = String(hi);
        });
        pmin.value = String(lo);
        pmax.value = String(hi);
        updateDualRangeLabels('price', lo, hi);
    }
    if (ymin && ymax) {
        ymin.min = String(meta.min_year);
        ymin.max = String(meta.max_year);
        ymax.min = String(meta.min_year);
        ymax.max = String(meta.max_year);
        ymin.value = String(meta.min_year);
        ymax.value = String(meta.max_year);
        updateDualRangeLabels('year', meta.min_year, meta.max_year);
    }
    if (mmin && mmax && meta.min_mileage != null && meta.max_mileage != null) {
        const lo = Number(meta.min_mileage);
        const hi = Number(meta.max_mileage);
        const step = 500;
        const loR = Math.floor(lo / step) * step;
        const hiR = Math.ceil(hi / step) * step;
        [mmin, mmax].forEach((el) => {
            el.min = String(loR);
            el.max = String(hiR);
        });
        mmin.value = String(loR);
        mmax.value = String(hiR);
        updateDualRangeLabels('mileage', loR, hiR);
    }

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
    if (!res.ok) return null;
    return res.json();
}

function updateResultsHintAndLoadMore() {
    const hint = document.getElementById('inventoryResultsHint');
    const wrap = document.getElementById('inventoryLoadMoreWrap');
    const btn = document.getElementById('loadMoreBtn');
    if (hint) {
        if (listTotal === 0) {
            hint.textContent = carData.length === 0 ? 'No listings match your filters.' : '';
        } else if (carData.length >= listTotal) {
            hint.textContent = `Showing all ${listTotal} listing${listTotal === 1 ? '' : 's'}`;
        } else {
            hint.textContent = `Showing ${carData.length} of ${listTotal} listings`;
        }
    }
    if (wrap && btn) {
        const hasMore = listTotal > 0 && carData.length < listTotal;
        wrap.hidden = !hasMore;
        btn.disabled = !hasMore;
        if (!btn.dataset.loading) btn.textContent = 'Load more';
    }
}

async function executeSearch({ append = false } = {}) {
    const list = document.getElementById('inventoryList');
    const hint = document.getElementById('inventoryResultsHint');
    const loadBtn = document.getElementById('loadMoreBtn');
    const q = document.getElementById('globalSearchInput')?.value.trim() || '';

    if (!append) {
        list.style.opacity = '0.55';
        list.innerHTML = '<div class="loading">Loading inventory…</div>';
    } else if (loadBtn) {
        loadBtn.dataset.loading = '1';
        loadBtn.disabled = true;
        loadBtn.textContent = 'Loading…';
    }

    const query = new URL('/api/cars', window.location.origin);
    if (q) query.searchParams.set('q', q);

    appendMultiParams(query, 'countries', Array.from(locSelection.countries));
    appendMultiParams(query, 'regions', Array.from(locSelection.regions));
    Array.from(locSelection.cities).forEach((key) => {
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
    if (inventoryMeta) {
        if (pmin > inventoryMeta.min_price) query.searchParams.set('min_price', String(pmin));
        if (pmax < inventoryMeta.max_price) query.searchParams.set('max_price', String(pmax));
    }

    const ymin = Number(document.getElementById('filterYearMin')?.value);
    const ymax = Number(document.getElementById('filterYearMax')?.value);
    if (inventoryMeta) {
        if (ymin > inventoryMeta.min_year) query.searchParams.set('min_year', String(ymin));
        if (ymax < inventoryMeta.max_year) query.searchParams.set('max_year', String(ymax));
    }

    const mmin = Number(document.getElementById('filterMileageMin')?.value);
    const mmax = Number(document.getElementById('filterMileageMax')?.value);
    if (inventoryMeta && inventoryMeta.min_mileage != null && inventoryMeta.max_mileage != null) {
        if (mmin > inventoryMeta.min_mileage) query.searchParams.set('min_mileage', String(Math.round(mmin)));
        if (mmax < inventoryMeta.max_mileage) query.searchParams.set('max_mileage', String(Math.round(mmax)));
    }

    appendMultiParams(query, 'body_styles', getSelectedChipValues('filterBodyTypes'));
    appendMultiParams(query, 'delivery_modes', getSelectedChipValues('filterDelivery'));
    appendMultiParams(query, 'conditions', getSelectedChipValues('filterConditions'));
    appendMultiParams(query, 'listing_formats', getSelectedChipValues('filterListingFormats'));

    const minRoi = document.getElementById('filterMinRoi')?.value.trim();
    const minProfit = document.getElementById('filterMinProfit')?.value.trim();
    if (minRoi) query.searchParams.set('min_roi', minRoi);
    if (minProfit) query.searchParams.set('min_profit', minProfit);

    const sortBy = document.getElementById('frontendSortBy')?.value || 'roi';
    query.searchParams.set('sort_by', sortBy);
    query.searchParams.set('sort_order', sortDesc ? 'desc' : 'asc');
    query.searchParams.set('limit', String(PAGE_SIZE));
    query.searchParams.set('offset', String(append ? carData.length : 0));

    try {
        const response = await fetch(query, { credentials: 'include' });
        if (response.status === 401) {
            window.location.replace('login.html');
            return;
        }
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = await response.json();
        const items = Array.isArray(payload.items) ? payload.items : [];
        listTotal = typeof payload.total === 'number' ? payload.total : items.length;
        if (append) {
            carData = carData.concat(items);
        } else {
            carData = items;
        }
        currentResults = carData;
        updateUI(currentResults);
        updateResultsHintAndLoadMore();
        if (!append) {
            requestAnimationFrame(() => scrollInventoryToTop());
        }
    } catch (err) {
        console.error('Search failed:', err);
        if (!append) {
            list.innerHTML =
                '<div class="no-results"><div>Connection error</div><div style="margin-top:8px;font-size:13px;">Unable to reach the server.</div></div>';
        }
        if (hint) hint.textContent = '';
    } finally {
        list.style.opacity = '1';
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
                `<img class="car-card-carousel-img" src="${attrEncode(url)}" alt="" data-slide="${i}" loading="lazy" ${i === 0 ? '' : 'hidden'}>`
        )
        .join('');
    const dots = imgs
        .map(
            (_, i) =>
                `<button type="button" class="car-card-carousel-dot" data-slide-to="${i}" aria-label="Photo ${i + 1}" aria-current="${i === 0 ? 'true' : 'false'}"></button>`
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
        <div class="car-card-carousel-dots">${dots}</div>`
            : '';
    return `<div class="car-card-carousel" data-carousel data-count="${imgs.length}">${slides}${nav}</div>`;
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

function specLines(car) {
    const body = car.body_style || '—';
    const drive = car.drive_type || '—';
    const title = car.vehicle_title || '—';
    return `
        <span class="car-card-spec-line">${escapeHtml(locationLine(car))}</span>
        <span class="car-card-spec-line">${escapeHtml(body)} · ${escapeHtml(drive)}</span>
        <span class="car-card-spec-line">Title: ${escapeHtml(title)}</span>
        <span class="car-card-spec-line">${escapeHtml(deliverySummary(car.delivery))}</span>
    `;
}

function updateUI(items) {
    const list = document.getElementById('inventoryList');
    if (items.length === 0) {
        list.innerHTML = '<div class="no-results"><div>No matches. Try widening filters or search.</div></div>';
        return;
    }

    list.innerHTML = items
        .map((car) => {
            const metricsStyle = metricsBlockHeatStyle(car.roi);
            const profitCls = profitValueClass(car.net_profit);
            return `
            <article class="car-card" data-car-id="${car.id}">
                <div class="car-card-media">
                    ${carouselHtml(car)}
                </div>
                <div class="car-card-body">
                    <div class="car-card-title-row">
                        <div class="car-card-title-year-col">
                            <span class="car-year-pill">${car.year}</span>
                        </div>
                        <span class="car-card-title-vrule" aria-hidden="true"></span>
                        <div class="car-card-title-main">
                            <h3 class="car-model">${escapeHtml(car.brand)} ${escapeHtml(car.model)}</h3>
                            <p class="car-card-subtitle">${escapeHtml(carSubtitleLine(car))}</p>
                        </div>
                    </div>
                    <div class="car-card-divider" aria-hidden="true"></div>
                    <div class="car-card-specs">${specLines(car)}</div>
                    <div class="car-card-divider" aria-hidden="true"></div>
                    <div class="car-card-footer">
                        ${priceBlockHtml(car)}
                        <div class="car-card-metrics-compact" style="${metricsStyle}">
                            <div class="car-card-metrics-col car-card-metrics-col--roi">
                                <span class="car-card-metrics-col-label">ROI</span>
                                <span class="car-card-metrics-col-value car-card-metrics-col-value--roi">${Number(car.roi).toFixed(1)}%</span>
                            </div>
                            <span class="car-card-metrics-divider" aria-hidden="true"></span>
                            <div class="car-card-metrics-col car-card-metrics-col--profit">
                                <span class="car-card-metrics-col-label">Est. net profit</span>
                                <span class="car-card-metrics-col-value ${profitCls}">${escapeHtml(formatMoney(car.net_profit))}</span>
                            </div>
                        </div>
                    </div>
                </div>
            </article>`;
        })
        .join('');

    list.querySelectorAll('.car-card').forEach((card) => {
        card.addEventListener('click', (e) => {
            if (e.target.closest('.car-card-carousel-nav, .car-card-carousel-dot')) {
                return;
            }
            const carId = Number(card.dataset.carId);
            const car = items.find((c) => c.id === carId);
            if (car) showCarDetails(car);
        });
    });

    list.querySelectorAll('[data-carousel]').forEach((root) => {
        const imgs = Array.from(root.querySelectorAll('.car-card-carousel-img'));
        const dots = Array.from(root.querySelectorAll('.car-card-carousel-dot'));
        const count = imgs.length;
        if (count < 2) return;
        let idx = 0;
        const show = (i) => {
            idx = (i + count) % count;
            imgs.forEach((img, j) => img.toggleAttribute('hidden', j !== idx));
            dots.forEach((d, j) => d.setAttribute('aria-current', j === idx ? 'true' : 'false'));
        };
        root.querySelector('.car-card-carousel-nav--prev')?.addEventListener('click', (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            show(idx - 1);
        });
        root.querySelector('.car-card-carousel-nav--next')?.addEventListener('click', (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            show(idx + 1);
        });
        dots.forEach((d) => {
            d.addEventListener('click', (ev) => {
                ev.preventDefault();
                ev.stopPropagation();
                show(Number(d.dataset.slideTo));
            });
        });
    });
}

function showCarDetails(car) {
    const modal = document.getElementById('itemModal');
    const header = document.getElementById('modalHeader');
    const content = document.getElementById('modalContent');

    header.textContent = `${car.brand} ${car.model} (${car.year})`;

    content.innerHTML = `
        <div style="display:flex;flex-direction:column;gap:16px;">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
                <div><div style="color:var(--text-muted);font-size:12px;margin-bottom:4px;">PURCHASE</div>
                    <div style="font-size:20px;font-weight:700;">$${car.price.toLocaleString()}</div></div>
                <div><div style="color:var(--text-muted);font-size:12px;margin-bottom:4px;">RESALE</div>
                    <div style="font-size:20px;font-weight:700;">$${car.resale_value.toLocaleString()}</div></div>
                <div><div style="color:var(--text-muted);font-size:12px;margin-bottom:4px;">REPAIR</div>
                    <div style="font-size:20px;font-weight:700;">$${car.repair_cost.toLocaleString()}</div></div>
                <div><div style="color:var(--text-muted);font-size:12px;margin-bottom:4px;">MILEAGE</div>
                    <div style="font-size:20px;font-weight:700;">${car.mileage != null ? car.mileage.toLocaleString() : 'N/A'} mi</div></div>
            </div>
            <div style="height:1px;background:var(--separator);"></div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
                <div style="background:var(--bg-page);padding:12px;border-radius:8px;">
                    <div style="color:var(--text-muted);font-size:12px;margin-bottom:4px;">EST. NET PROFIT</div>
                    <div style="font-size:24px;font-weight:700;color:${car.net_profit >= 0 ? 'var(--accent-green)' : '#ef4444'};">
                        ${car.net_profit >= 0 ? '+' : ''}$${car.net_profit.toLocaleString()}
                    </div>
                </div>
                <div style="background:var(--bg-page);padding:12px;border-radius:8px;">
                    <div style="color:var(--text-muted);font-size:12px;margin-bottom:4px;">ROI</div>
                    <div style="font-size:24px;font-weight:700;color:${car.roi >= 0 ? 'var(--accent-green)' : '#ef4444'};">${car.roi}%</div>
                </div>
            </div>
        </div>`;

    modal.classList.add('active');
}

function hideModal() {
    document.getElementById('itemModal').classList.remove('active');
}

function resetFilters() {
    document.getElementById('globalSearchInput').value = '';
    document.querySelectorAll('.filter-chip').forEach((b) => b.setAttribute('aria-pressed', 'false'));
    document.getElementById('filterMinRoi').value = '';
    document.getElementById('filterMinProfit').value = '';
    makeSelection.clear();
    clearLocationSelections();
    if (inventoryMeta) populateMetaIntoUi(inventoryMeta);
    applyLocationSingletonDefaults({ onlyIfEmpty: true });
    refreshRegionOptions();
    refreshCityOptions();
    updateRadiusAvailability();
    updateMakeTriggerLabel();
    const rlab = document.getElementById('filterRadiusMiLabel');
    const rIn = document.getElementById('filterRadiusMi');
    if (rIn && rlab) rlab.textContent = rIn.value;
    executeSearch({ append: false });
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
    document.addEventListener('click', () => {
        menu.hidden = true;
        btn.setAttribute('aria-expanded', 'false');
    });
}

function scheduleGlobalSearch() {
    clearTimeout(globalSearchTimer);
    globalSearchTimer = setTimeout(() => executeSearch({ append: false }), 380);
}

function initEventListeners() {
    document.getElementById('themeToggleBtn')?.addEventListener('click', toggleTheme);
    document.getElementById('applyFiltersBtn')?.addEventListener('click', () => executeSearch({ append: false }));
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
    document.getElementById('globalSearchBtn')?.addEventListener('click', () => executeSearch({ append: false }));
    document.getElementById('globalSearchInput')?.addEventListener('input', scheduleGlobalSearch);
    document.getElementById('globalSearchInput')?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            clearTimeout(globalSearchTimer);
            executeSearch({ append: false });
        }
    });

    document.getElementById('filterRadiusMi')?.addEventListener('input', (e) => {
        const lab = document.getElementById('filterRadiusMiLabel');
        if (lab) lab.textContent = e.target.value;
    });

    initAccountMenu();
}

document.addEventListener('DOMContentLoaded', async () => {
    try {
        const res = await fetch('/api/auth/me', { credentials: 'include' });
        if (res.status === 401) {
            window.location.replace('login.html');
            return;
        }
        if (!res.ok) throw new Error('session_check_failed');
        const me = await res.json();
        const label = document.getElementById('accountEmailLabel');
        if (label && me.email) label.textContent = me.email;
    } catch {
        window.location.replace('login.html');
        return;
    }

    initTheme();
    initViewMode();
    initSortOrderUi();
    initFilterDropdowns();
    initEventListeners();

    wireDualRange('price', document.getElementById('filterPriceMin'), document.getElementById('filterPriceMax'));
    wireDualRange('year', document.getElementById('filterYearMin'), document.getElementById('filterYearMax'));
    wireDualRange('mileage', document.getElementById('filterMileageMin'), document.getElementById('filterMileageMax'));

    const meta = await fetchMeta();
    if (meta) populateMetaIntoUi(meta);
    applyLocationSingletonDefaults({ onlyIfEmpty: true });
    refreshRegionOptions();
    refreshCityOptions();
    updateRadiusAvailability();
    updateLocationTierUi();

    executeSearch({ append: false });
});
