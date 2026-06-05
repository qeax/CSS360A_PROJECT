/**
 * Car detail page — gallery, lightbox, sanitized description, actions.
 */

function listingUi() {
    return window.Css360Listing || {};
}

const CAROUSEL_NAV_PREV = `<button type="button" class="car-card-carousel-nav car-card-carousel-nav--prev" aria-label="Previous photo">
    <svg class="car-card-carousel-nav-svg" width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7"/></svg>
</button>`;
const CAROUSEL_NAV_NEXT = `<button type="button" class="car-card-carousel-nav car-card-carousel-nav--next" aria-label="Next photo">
    <svg class="car-card-carousel-nav-svg" width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"/></svg>
</button>`;

function carIdFromQuery() {
    const params = new URLSearchParams(window.location.search);
    return parseCarId(params.get('id'));
}

function showCarDetailError(message) {
    const root = document.getElementById('carDetailRoot');
    if (root) {
        root.innerHTML = `<div class="car-detail-error">${listingUi().escapeHtml ? listingUi().escapeHtml(message) : message}</div>`;
    }
}

async function fetchCarDetail(rawId) {
    const carId = parseCarId(rawId);
    if (!carId) {
        throw new Error('invalid_car_id');
    }
    const url = `/api/cars/${carId}`;
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 20000);
    try {
        return await fetch(url, {
            credentials: 'include',
            signal: controller.signal,
        });
    } finally {
        window.clearTimeout(timer);
    }
}

function backHref() {
    const params = new URLSearchParams(window.location.search);
    const ret = params.get('return');
    if (ret && !ret.includes('://') && !ret.startsWith('//')) return ret;
    return 'index.html';
}

function showEbayToast(message, opts = {}) {
    const stack = document.getElementById('appToastStack');
    if (!stack || !message) return;
    const variant = opts.variant === 'warn' ? 'warn' : 'error';
    const el = document.createElement('div');
    el.className = `app-toast app-toast--${variant}`;
    el.setAttribute('role', 'status');
    el.textContent = message;
    stack.appendChild(el);
    window.setTimeout(() => {
        el.classList.add('is-hiding');
        window.setTimeout(() => el.remove(), 400);
    }, opts.durationMs ?? 5000);
}

async function toggleWatch(carId, isWatched) {
    const url = `/api/watchlist/${carId}`;
    const res = await fetch(url, {
        method: isWatched ? 'DELETE' : 'POST',
        credentials: 'include',
    });
    if (res.status === 409) {
        showEbayToast('You can track at most 10 listings. Remove one from Profile first.', {
            variant: 'warn',
        });
        return isWatched;
    }
    if (!res.ok) throw new Error(`watch ${res.status}`);
    return !isWatched;
}

async function initGalleryLightbox(root, images) {
    if (!images.length) return;
    const { default: PhotoSwipeLightbox } = await import(
        'https://cdn.jsdelivr.net/npm/photoswipe@5.4.4/dist/photoswipe-lightbox.esm.min.js'
    );
    const lb = new PhotoSwipeLightbox({
        gallery: root,
        children: 'a.car-detail-lightbox-link.is-active[data-pswp-src]',
        pswpModule: () => import('https://cdn.jsdelivr.net/npm/photoswipe@5.4.4/dist/photoswipe.esm.min.js'),
    });
    lb.init();
}

function buildDescriptionSection(car) {
    if (car.description_html) {
        return `<section class="car-detail-description"><h2 class="car-detail-section-title">Description</h2><div class="listing-description listing-description--html" id="listingDescriptionHtml"></div></section>`;
    }
    return '';
}

function isFullHtmlDocument(html) {
    const trimmed = String(html).trim();
    if (!trimmed) return false;
    if (/^<!DOCTYPE/i.test(trimmed) || /^<html[\s>]/i.test(trimmed)) return true;
    return /<head[\s>]/i.test(trimmed.slice(0, 4000));
}

function resizeDescriptionIframe(iframe) {
    try {
        const doc = iframe.contentDocument;
        const height = Math.max(
            doc?.documentElement?.scrollHeight || 0,
            doc?.body?.scrollHeight || 0,
            120,
        );
        iframe.style.height = `${height}px`;
    } catch (_) {
        iframe.style.minHeight = '200px';
    }
}

function mountListingDescription(container, html) {
    if (!container || !html) return;
    const trimmed = String(html).trim();
    container.innerHTML = '';

    if (!/<[a-z!/]/i.test(trimmed)) {
        const p = document.createElement('p');
        p.className = 'listing-description-plain';
        p.textContent = trimmed;
        container.appendChild(p);
        return;
    }

    if (isFullHtmlDocument(trimmed)) {
        const iframe = document.createElement('iframe');
        iframe.className = 'listing-description-iframe';
        iframe.setAttribute('title', 'Listing description');
        iframe.setAttribute('sandbox', 'allow-same-origin');
        iframe.setAttribute('loading', 'lazy');
        iframe.srcdoc = trimmed;
        iframe.addEventListener('load', () => resizeDescriptionIframe(iframe));
        container.appendChild(iframe);
        return;
    }

    container.innerHTML = trimmed;
}

function peekSlideHtml(url, opts = {}) {
    const { loading = 'lazy', isClone = false, isActive = false, realIndex = 0 } = opts;
    const cloneCls = isClone ? ' is-clone' : '';
    const activeCls = isActive ? ' is-active' : '';
    return `<a href="${listingUi().escapeAttr(url)}" data-pswp-src="${listingUi().escapeAttr(url)}" data-pswp-width="1600" data-pswp-height="1200" class="car-detail-lightbox-link${cloneCls}${activeCls}" data-real-index="${realIndex}">
        <img class="car-card-carousel-img" src="${listingUi().escapeAttr(url)}" alt="" loading="${loading}" draggable="false" />
    </a>`;
}

function galleryHtmlWithLightbox(car) {
    const images = Array.isArray(car.images) && car.images.length ? car.images : car.image_url ? [car.image_url] : [];
    if (!images.length) {
        return '<div class="car-card-carousel car-card-carousel--empty"><div class="car-card-carousel-placeholder">No photo</div></div>';
    }
    if (images.length === 1) {
        return `<div class="car-card-carousel car-card-carousel--single">
            <div class="car-card-carousel-viewport">
                ${peekSlideHtml(images[0], { loading: 'eager', isActive: true, realIndex: 0 })}
            </div>
        </div>`;
    }
    const ordered = [images[images.length - 1], ...images, images[0]];
    const slides = ordered
        .map((url, stripIdx) => {
            let realIndex = stripIdx - 1;
            if (stripIdx === 0) realIndex = images.length - 1;
            if (stripIdx === ordered.length - 1) realIndex = 0;
            const isClone = stripIdx === 0 || stripIdx === ordered.length - 1;
            const isActive = stripIdx === 1;
            return peekSlideHtml(url, {
                loading: stripIdx <= 2 ? 'eager' : 'lazy',
                isClone,
                isActive,
                realIndex,
            });
        })
        .join('');
    return `<div class="car-card-carousel car-detail-peek-carousel" data-carousel="detail-peek" data-count="${images.length}">
        <div class="car-card-carousel-viewport">
            <div class="car-card-carousel-strip">${slides}</div>
        </div>
        ${CAROUSEL_NAV_PREV}
        ${CAROUSEL_NAV_NEXT}
    </div>`;
}

function initCarDetailPeekCarousel(root, images) {
    const carousel = root?.querySelector('[data-carousel="detail-peek"]');
    if (!carousel || images.length < 2) return;

    const strip = carousel.querySelector('.car-card-carousel-strip');
    const viewport = carousel.querySelector('.car-card-carousel-viewport');
    const slides = Array.from(strip?.querySelectorAll('.car-detail-lightbox-link') || []);
    const count = images.length;
    if (!strip || !viewport || slides.length < 3) return;

    let stripIndex = 1;

    const centerSlide = (idx, animate = true) => {
        const slide = slides[idx];
        if (!slide) return;
        slides.forEach((s, i) => s.classList.toggle('is-active', i === idx));
        const viewportWidth = viewport.offsetWidth;
        if (!viewportWidth || !slide.offsetWidth) return;
        const slideCenter = slide.offsetLeft + slide.offsetWidth / 2;
        const offset = slideCenter - viewportWidth / 2;
        if (!animate) strip.classList.add('is-no-transition');
        strip.style.transform = `translate3d(${-offset}px, 0, 0)`;
        if (!animate) {
            strip.offsetHeight;
            strip.classList.remove('is-no-transition');
        }
    };

    const jumpWithoutAnim = (idx) => {
        stripIndex = idx;
        centerSlide(stripIndex, false);
    };

    const goTo = (idx) => {
        stripIndex = idx;
        centerSlide(stripIndex, true);
    };

    strip.addEventListener('transitionend', (e) => {
        if (e.target !== strip || e.propertyName !== 'transform') return;
        if (stripIndex === 0) jumpWithoutAnim(count);
        else if (stripIndex === count + 1) jumpWithoutAnim(1);
    });

    carousel.querySelector('.car-card-carousel-nav--prev')?.addEventListener('click', (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        goTo(stripIndex - 1);
    });

    carousel.querySelector('.car-card-carousel-nav--next')?.addEventListener('click', (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        goTo(stripIndex + 1);
    });

    slides.forEach((link, idx) => {
        link.addEventListener('click', (ev) => {
            if (!link.classList.contains('is-active')) {
                ev.preventDefault();
                goTo(idx);
            }
        });
    });

    let touchStartX = null;
    viewport.addEventListener(
        'touchstart',
        (ev) => {
            touchStartX = ev.changedTouches[0]?.clientX ?? null;
        },
        { passive: true },
    );
    viewport.addEventListener(
        'touchend',
        (ev) => {
            if (touchStartX == null) return;
            const dx = (ev.changedTouches[0]?.clientX ?? touchStartX) - touchStartX;
            touchStartX = null;
            if (Math.abs(dx) < 40) return;
            if (dx < 0) goTo(stripIndex + 1);
            else goTo(stripIndex - 1);
        },
        { passive: true },
    );

    const onResize = () => centerSlide(stripIndex, false);
    window.addEventListener('resize', onResize);
    requestAnimationFrame(() => jumpWithoutAnim(1));
}

function refreshEbayErrorMessage(detail) {
    if (detail === 'ebay_rate_limited') {
        return 'eBay rate limit reached. Wait a moment and try again.';
    }
    if (typeof detail === 'string' && detail.startsWith('ebay_get_item_failed')) {
        return 'eBay is temporarily unavailable. Try again in a moment.';
    }
    if (detail === 'ebay_not_configured') {
        return 'eBay integration is not configured on the server.';
    }
    if (typeof detail === 'string') {
        return `Refresh failed: ${detail}`;
    }
    return 'Failed to refresh from eBay.';
}

function renderPage(car) {
    const root = document.getElementById('carDetailRoot');
    const ui = listingUi();
    if (!root || !window.Css360Listing) return;
    if (typeof ui.stopAuctionCountdownTimer === 'function') {
        ui.stopAuctionCountdownTimer();
    }
    const settings = getSettings();
    const showEconomics = ui.shouldShowEconomics(car);
    const economicsNoteHtml =
        showEconomics && typeof ui.resaleEstimateDetailHtml === 'function'
            ? ui.resaleEstimateDetailHtml(car)
            : '';
    const metricsHtml = showEconomics
        ? `<div class="car-detail-pricing-metrics">${ui.metricsBlockHtml(car)}</div>`
        : '';
    const descHtml = buildDescriptionSection(car);
    const summaryLine = car.description_summary
        ? `<p class="car-detail-summary">${ui.escapeHtml(car.description_summary)}</p>`
        : '';
    const watchHeart =
        typeof ui.watchHeartButtonHtml === 'function'
            ? ui.watchHeartButtonHtml(car, Boolean(car.is_watched), 'id="detailWatchBtn"')
            : '';
    const isEbay = car.source === 'ebay' && car.external_listing_id;
    const ebayBtn = ui.listingLinkButtonHtml(car);
    const refreshBtn = isEbay
        ? '<button type="button" class="modal-refresh-btn" id="detailRefreshEbayBtn">Refresh from eBay</button>'
        : '';
    const resaleBtn = showEconomics
        ? '<button type="button" class="modal-resale-btn" id="detailResaleRefreshBtn">Recalculate resale</button>'
        : '';
    const deleteBtn = settings.showDeleteCarButton
        ? '<button type="button" class="modal-delete-btn" id="detailDeleteCarBtn">Delete from database</button>'
        : '';
    const jsonBtn = settings.showListingJsonDebug
        ? '<button type="button" class="modal-json-debug-btn" id="detailViewRawJsonBtn">View raw JSON</button>'
        : '';
    const actionBtns = [ebayBtn, refreshBtn, resaleBtn, deleteBtn, jsonBtn].filter(Boolean).join('');
    const images = Array.isArray(car.images) && car.images.length ? car.images : car.image_url ? [car.image_url] : [];
    const vehicleDetailsHtml =
        typeof ui.modalVehicleDetailsHtml === 'function' ? ui.modalVehicleDetailsHtml(car) : '';

    const displayTitle =
        (typeof car.listing_title === 'string' && car.listing_title.trim()) ||
        `${car.brand || ''} ${car.model || ''}`.trim() ||
        'Listing';
    const secondaryTitle = `${car.brand || ''} ${car.model || ''}`.trim();
    root.innerHTML = `
        <a class="car-detail-back" href="${ui.escapeAttr(backHref())}">← Back to inventory</a>
        <div class="car-detail-hero" id="carGallery">${galleryHtmlWithLightbox(car)}</div>
        <div class="car-detail-title-panel">
            <div class="car-detail-title-row">
                <span class="car-year-pill">${car.year != null ? ui.escapeHtml(String(car.year)) : '—'}</span>
                <span class="car-card-title-vrule" aria-hidden="true"></span>
                <div class="car-detail-title-main">
                    <h1 class="car-detail-title">${ui.escapeHtml(displayTitle)}</h1>
                    ${secondaryTitle && secondaryTitle !== displayTitle ? `<p class="car-detail-summary">${ui.escapeHtml(secondaryTitle)}</p>` : ''}
                    <p class="car-detail-subtitle">${ui.escapeHtml(ui.carSubtitleLine(car))}</p>
                    ${summaryLine}
                </div>
                ${watchHeart}
            </div>
        </div>
        <div class="car-detail-body">
            <div class="car-detail-divider" aria-hidden="true"></div>
            <div class="car-detail-pricing-row">
                ${ui.priceBlockHtml(car)}
                ${metricsHtml}
            </div>
            ${economicsNoteHtml}
            <div class="car-detail-divider" aria-hidden="true"></div>
            <div class="car-detail-cta-stack">
                ${actionBtns ? `<div class="car-detail-actions-row">${actionBtns}</div>` : ''}
                <pre class="car-detail-raw-json" id="detailRawJsonPre" hidden></pre>
            </div>
            ${vehicleDetailsHtml}
            ${descHtml}
        </div>`;

    if (car.description_html) {
        const descEl = document.getElementById('listingDescriptionHtml');
        if (descEl) mountListingDescription(descEl, car.description_html);
    }

    const gallery = document.getElementById('carGallery');
    if (gallery) {
        try {
            if (images.length >= 2) {
                initCarDetailPeekCarousel(gallery, images);
            }
            void initGalleryLightbox(gallery, images).catch((err) => {
                console.error('Gallery init failed:', err);
            });
        } catch (err) {
            console.error('Gallery init failed:', err);
        }
    }

    document.getElementById('detailWatchBtn')?.addEventListener('click', async () => {
        const btn = document.getElementById('detailWatchBtn');
        try {
            const next = await toggleWatch(car.id, car.is_watched);
            car.is_watched = next;
            btn.classList.toggle('is-watched', next);
            btn.setAttribute('aria-pressed', next ? 'true' : 'false');
            btn.setAttribute('aria-label', next ? 'Remove from watchlist' : 'Add to watchlist');
        } catch (e) {
            console.error(e);
        }
    });

    document.getElementById('detailResaleRefreshBtn')?.addEventListener('click', async () => {
        const btn = document.getElementById('detailResaleRefreshBtn');
        btn.disabled = true;
        btn.textContent = 'Recalculating…';
        try {
            const res = await fetch(`/api/cars/${car.id}/resale-refresh`, {
                method: 'POST',
                credentials: 'include',
            });
            if (res.status === 401) {
                window.location.replace('login.html');
                return;
            }
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                const msg =
                    (typeof data.detail === 'object' && data.detail?.message) ||
                    (typeof data.detail === 'string' && data.detail) ||
                    `HTTP ${res.status}`;
                throw new Error(msg);
            }
            try {
                const key = 'css360_inventory_session_v1';
                const raw = sessionStorage.getItem(key);
                if (raw) {
                    const payload = JSON.parse(raw);
                    if (Array.isArray(payload?.carData)) {
                        const idx = payload.carData.findIndex((x) => Number(x?.id) === Number(data.item?.id));
                        if (idx >= 0) {
                            payload.carData[idx] = data.item;
                            payload.savedAt = Date.now();
                            sessionStorage.setItem(key, JSON.stringify(payload));
                        }
                    }
                }
            } catch (err2) {
                console.warn('Failed to patch inventory session after resale refresh', err2);
            }
            renderPage(data.item);
        } catch (err) {
            console.error(err);
            showEbayToast(err.message || 'Failed to recalculate resale.', { variant: 'error' });
            btn.disabled = false;
            btn.textContent = 'Recalculate resale';
        }
    });

    document.getElementById('detailRefreshEbayBtn')?.addEventListener('click', async () => {
        const btn = document.getElementById('detailRefreshEbayBtn');
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
            const data = await res.json().catch(() => ({}));
            if (data.deleted) {
                showEbayToast(data.message || 'Listing removed from eBay.', { variant: 'warn' });
                window.location.href = backHref();
                return;
            }
            if (!res.ok) {
                throw new Error(refreshEbayErrorMessage(data.detail));
            }
            try {
                const key = 'css360_inventory_session_v1';
                const raw = sessionStorage.getItem(key);
                if (raw) {
                    const payload = JSON.parse(raw);
                    if (Array.isArray(payload?.carData)) {
                        const idx = payload.carData.findIndex((x) => Number(x?.id) === Number(data.item?.id));
                        if (idx >= 0) {
                            payload.carData[idx] = data.item;
                            payload.savedAt = Date.now();
                            sessionStorage.setItem(key, JSON.stringify(payload));
                        }
                    }
                }
            } catch (err2) {
                console.warn('Failed to patch inventory session after refresh', err2);
            }
            renderPage(data.item);
        } catch (err) {
            console.error(err);
            showEbayToast(err.message || 'Failed to refresh from eBay.', { variant: 'error' });
            btn.disabled = false;
            btn.textContent = 'Refresh from eBay';
        }
    });

    document.getElementById('detailDeleteCarBtn')?.addEventListener('click', async () => {
        if (!window.confirm('Delete this listing from the database?')) return;
        const res = await fetch(`/api/cars/${car.id}`, { method: 'DELETE', credentials: 'include' });
        if (res.status === 204) window.location.href = backHref();
    });

    document.getElementById('detailViewRawJsonBtn')?.addEventListener('click', async () => {
        const pre = document.getElementById('detailRawJsonPre');
        const btn = document.getElementById('detailViewRawJsonBtn');
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

    if (typeof ui.startAuctionCountdownTimer === 'function') {
        ui.startAuctionCountdownTimer();
    }
}

async function main() {
    const carId = carIdFromQuery();

    if (!window.Css360Listing) {
        showCarDetailError('Page scripts failed to load. Hard-refresh (Ctrl+F5).');
        return;
    }
    if (!carId) {
        showCarDetailError('Missing listing id.');
        return;
    }

    try {
        initAppShell();
        const me = await requireAuth();
        if (!me) {
            showCarDetailError('Session expired. Redirecting to login…');
            return;
        }
        setNotificationsBadge(me.notifications_unread_count);
        void runWatchCheckIfDue();

        const res = await fetchCarDetail(carId);
        if (res.status === 401) {
            window.location.replace('login.html');
            return;
        }
        if (res.status === 404) {
            showCarDetailError('Listing not found.');
            return;
        }
        if (res.status === 422) {
            showCarDetailError(`Invalid listing id in URL (id=${carId}).`);
            return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const pageTitle =
            (typeof data.item.listing_title === 'string' && data.item.listing_title.trim()) ||
            `${data.item.brand || ''} ${data.item.model || ''}`.trim() ||
            'Listing';
        document.title = `${pageTitle} · Car Flip CSS360`;
        try {
            renderPage(data.item);
        } catch (renderErr) {
            console.error(renderErr);
            showCarDetailError('Failed to render listing.');
        }
    } catch (err) {
        console.error(err);
        let msg = 'Failed to load listing.';
        if (err && err.name === 'AbortError') {
            msg = 'Listing request timed out. Try again.';
        } else if (err && err.message === 'invalid_car_id') {
            msg = 'Invalid listing id in URL.';
        }
        showCarDetailError(msg);
    }
}

main();
