/**
 * Shared listing UI helpers for CSS360 inventory cards and modals.
 */
(function () {
    'use strict';

    const MAX_CAROUSEL_DOTS = 7;
    const CAROUSEL_DOTS_CENTER_IDX = 3;

    const DELIVERY_CHIPS = [
        { value: 'ship', label: 'Ship to home' },
        { value: 'local_pickup', label: 'Local pickup' },
        { value: 'in_store', label: 'In-store pickup' },
    ];

    const LISTING_FORMAT_LABELS = {
        AUCTION: 'Auction',
        BUY_IT_NOW: 'Buy it now',
        FIXED_PRICE: 'Buy it now',
        CLASSIFIED_AD: 'Classified ads',
        ACCEPTS_OFFER: 'Accepts offer',
    };

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

    function attrEncode(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function formatMoney(n) {
        if (n == null || Number.isNaN(n)) return '—';
        const rounded = Math.round(n);
        const sign = rounded >= 0 ? '+' : '−';
        return `${sign}$${Math.abs(rounded).toLocaleString()}`;
    }

    function formatPriceShort(n) {
        return `$${Math.round(Number(n)).toLocaleString()}`;
    }

    function formatMileageDisplay(car) {
        if (car.mileage == null) return 'Mileage unknown';
        return `${Number(car.mileage).toLocaleString()} mi`;
    }

    function isPriceKnown(car) {
        return car && car.price_known !== false;
    }

    function shouldShowEconomics(car) {
        return isPriceKnown(car) && !car.auction_ended;
    }

    function isRoiPreliminary(car) {
        return Boolean(car && car.roi_is_preliminary);
    }

    function roiPreliminaryTooltip(car) {
        const bid =
            car.price != null && !Number.isNaN(Number(car.price))
                ? formatPriceShort(car.price)
                : '—';
        const est =
            car.purchase_price_effective != null &&
            !Number.isNaN(Number(car.purchase_price_effective))
                ? formatPriceShort(car.purchase_price_effective)
                : '—';
        return `ROI is based on estimated acquisition price (${est}). Current bid: ${bid}.`;
    }

    function roiPreliminaryBadgeHtml(car) {
        if (!isRoiPreliminary(car)) return '';
        const tip = roiPreliminaryTooltip(car);
        return `<span class="car-card-roi-preliminary" title="${escapeAttr(tip)}" tabindex="0" aria-label="${escapeAttr(`Preliminary ROI. ${tip}`)}">Preliminary</span>`;
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

    function calculateHeatmap(roi, brightness = 42, saturation = 65) {
        const score = Math.min(Math.max(roi, 0), 30);
        const hue = (score / 30) * 120;
        return `hsl(${hue}, ${saturation}%, ${brightness}%)`;
    }

    function calculateHeatmapBorder(roi) {
        return calculateHeatmap(roi, 32, 55);
    }

    function metricsBlockHeatStyle(roi, priceKnown = true, confidence = null, roiPreliminary = false) {
        if (priceKnown === false || roi == null || Number.isNaN(Number(roi))) {
            return 'background: var(--bg-page); border-color: var(--border-color);';
        }
        const heat = calculateHeatmap(roi, 40, 58);
        const border = calculateHeatmapBorder(roi);
        let mixPct = 22;
        const conf = Number(confidence);
        if (!Number.isNaN(conf) && conf > 0) {
            if (conf < 0.45) mixPct = 12;
            else if (conf < 0.75) mixPct = 17;
        }
        if (roiPreliminary) {
            mixPct = Math.min(mixPct, 10);
        }
        return `background: color-mix(in srgb, ${heat} ${mixPct}%, var(--bg-page)); border-color: color-mix(in srgb, ${border} 55%, var(--border-color));`;
    }

    function formatResaleMethodLabel(method) {
        const key = String(method || '')
            .trim()
            .toLowerCase();
        if (!key) return '';
        if (key === 'comps_tight' || key === 'comps') return 'Comps';
        if (key === 'comps_shrunk') return 'Comps (shrunk)';
        if (key === 'segment') return 'Segment baseline';
        if (key === 'heuristic') return 'Heuristic';
        if (key === 'external') return 'External';
        return key.replace(/_/g, ' ');
    }

    function formatResaleConfidence(confidence) {
        const conf = Number(confidence);
        if (Number.isNaN(conf) || conf <= 0) {
            return { label: '', tier: '' };
        }
        if (conf >= 0.75) return { label: 'High', tier: 'high' };
        if (conf >= 0.45) return { label: 'Medium', tier: 'medium' };
        return { label: 'Low', tier: 'low' };
    }

    function resaleConfidenceTooltip(tier) {
        if (tier === 'high') {
            return 'High confidence: several close, recent comparable listings in our inventory support this resale estimate. ROI and profit are relatively trustworthy.';
        }
        if (tier === 'medium') {
            return 'Medium confidence: estimate comes from comparable listings or a segment average, but with fewer matches or looser similarity. Use ROI as a reasonable guide, not a precise target.';
        }
        if (tier === 'low') {
            return 'Low confidence: little or no comparable inventory data; estimate relies mainly on heuristics (year, mileage, condition, asking price). Treat ROI and profit as directional only.';
        }
        return '';
    }

    function resaleEstimateMetaParts(car) {
        const methodLabel = formatResaleMethodLabel(car.resale_method);
        const compCount = Number(car.resale_comp_count || 0);
        const conf = formatResaleConfidence(car.resale_confidence);
        const parts = [];
        if (methodLabel) parts.push(methodLabel);
        if (compCount > 0 && String(car.resale_method || '').toLowerCase().startsWith('comps')) {
            parts.push(`${compCount} comp${compCount === 1 ? '' : 's'}`);
        } else if (compCount > 0 && String(car.resale_method || '').toLowerCase() === 'segment') {
            parts.push(`${compCount} in segment`);
        }
        if (conf.label) parts.push(conf.label);
        return { parts, conf, methodLabel, compCount };
    }

    function resaleEstimateMetaHtml(car) {
        const { parts, conf } = resaleEstimateMetaParts(car);
        if (!parts.length) return '';
        const text = parts.join(' · ');
        const dotCls = conf.tier ? ` car-card-metrics-meta-dot--${conf.tier}` : '';
        return `<span class="car-card-metrics-meta" title="Resale estimate source and confidence">
            <span class="car-card-metrics-meta-dot${dotCls}" aria-hidden="true"></span>
            <span class="car-card-metrics-meta-text">${escapeHtml(text)}</span>
        </span>`;
    }

    function resaleEstimateDetailHtml(car) {
        if (!shouldShowEconomics(car)) return '';
        const methodKey = String(car.resale_method || '')
            .trim()
            .toLowerCase();
        const methodLabel = formatResaleMethodLabel(car.resale_method) || 'Estimate';
        const { conf, compCount } = resaleEstimateMetaParts(car);
        const resaleDisplay =
            car.resale_value != null && !Number.isNaN(Number(car.resale_value))
                ? formatPriceShort(car.resale_value)
                : '—';
        const repairDisplay =
            car.repair_cost != null && !Number.isNaN(Number(car.repair_cost))
                ? formatPriceShort(car.repair_cost)
                : '—';

        let lead = 'Resale estimate uses available inventory data.';
        if (methodKey === 'comps_tight' || methodKey === 'comps') {
            lead =
                compCount > 0
                    ? `Estimated by ${methodLabel} from ${compCount} similar listing${compCount === 1 ? '' : 's'} in our inventory.`
                    : `Estimated by ${methodLabel} from similar listings in our inventory.`;
        } else if (methodKey === 'comps_shrunk') {
            lead = `Estimated by ${methodLabel} — a blend of similar listings and segment pricing.`;
        } else if (methodKey === 'segment') {
            lead =
                compCount > 0
                    ? `Estimated from segment baseline (${compCount} listing${compCount === 1 ? '' : 's'} in this make/model/year group).`
                    : 'Estimated from segment baseline for this make, model, and year.';
        } else if (methodKey === 'heuristic') {
            lead = 'Limited comparable data — estimate uses listing age, mileage, condition, and purchase price.';
        }

        const confTooltip = resaleConfidenceTooltip(conf.tier);

        const confBadge = conf.label
            ? `<span class="car-detail-economics-confidence car-detail-economics-confidence--${escapeAttr(conf.tier)}" title="${escapeAttr(confTooltip)}" tabindex="0" aria-label="${escapeAttr(`${conf.label} confidence. ${confTooltip}`)}">${escapeHtml(conf.label)} confidence</span>`
            : '';

        const preliminaryBadge = isRoiPreliminary(car)
            ? `<span class="car-detail-economics-confidence car-detail-economics-confidence--low" title="${escapeAttr(roiPreliminaryTooltip(car))}" tabindex="0">Preliminary ROI</span>`
            : '';

        const purchaseRows = isRoiPreliminary(car)
            ? `<div class="car-detail-economics-dl-row">
                    <dt>Current bid</dt>
                    <dd>${escapeHtml(formatPriceShort(car.price))}</dd>
                </div>
                <div class="car-detail-economics-dl-row">
                    <dt>Est. acquisition</dt>
                    <dd>${escapeHtml(formatPriceShort(car.purchase_price_effective))} — used for ROI when the bid is unrealistically low</dd>
                </div>`
            : '';

        return `<section class="car-detail-economics-note" aria-label="How resale and ROI were estimated">
            <h2 class="car-detail-economics-note-title">How we estimated resale</h2>
            <p class="car-detail-economics-note-lead">${escapeHtml(lead)}</p>
            ${confBadge}
            ${preliminaryBadge}
            <dl class="car-detail-economics-dl">
                ${purchaseRows}
                <div class="car-detail-economics-dl-row">
                    <dt>Resale (est.)</dt>
                    <dd>${escapeHtml(resaleDisplay)} — expected price after reconditioning</dd>
                </div>
                <div class="car-detail-economics-dl-row">
                    <dt>Repair (est.)</dt>
                    <dd>${escapeHtml(repairDisplay)} — expected reconditioning cost</dd>
                </div>
                <div class="car-detail-economics-dl-row">
                    <dt>ROI (est.)</dt>
                    <dd>${escapeHtml(formatRoiDisplay(car))}${isRoiPreliminary(car) ? ' — preliminary, based on estimated acquisition price' : ' — return based on purchase, repair, and resale'}</dd>
                </div>
            </dl>
            <p class="car-detail-economics-note-foot car-detail-economics-note-foot--muted">Comparable prices reflect asking prices from eBay listings, not final sold prices.</p>
        </section>`;
    }

    function profitValueClass(n) {
        if (n == null || Number.isNaN(n) || n === 0) return '';
        return n > 0 ? 'car-card-metrics-col-value--positive' : 'car-card-metrics-col-value--negative';
    }

    function metricsBlockHtml(car) {
        if (!shouldShowEconomics(car)) {
            return '';
        }
        const roiLabel = (car.source || '').toLowerCase() === 'ebay' ? 'ROI (est.)' : 'ROI';
        const profitCls = profitValueClass(car.net_profit);
        const metaHtml = resaleEstimateMetaHtml(car);
        const prelimBadge = roiPreliminaryBadgeHtml(car);
        return `<div class="car-card-metrics-compact" style="${metricsBlockHeatStyle(car.roi, true, car.resale_confidence, isRoiPreliminary(car))}">
            <div class="car-card-metrics-col car-card-metrics-col--roi">
                <span class="car-card-metrics-col-label">${escapeHtml(roiLabel)}</span>
                <span class="car-card-metrics-col-value car-card-metrics-col-value--roi">${escapeHtml(formatRoiDisplay(car))}${prelimBadge}</span>
                ${metaHtml}
            </div>
            <span class="car-card-metrics-divider" aria-hidden="true"></span>
            <div class="car-card-metrics-col car-card-metrics-col--profit">
                <span class="car-card-metrics-col-label">Est. net profit</span>
                <span class="car-card-metrics-col-value ${profitCls}">${escapeHtml(formatProfitDisplay(car))}</span>
            </div>
        </div>`;
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
        if (u.includes('ACCEPT') && u.includes('OFFER')) return 'Accepts offer';
        if (u.includes('CLASSIFIED')) return 'Classified ads';
        if (u.includes('AUCTION')) return 'Auction';
        if (u.includes('FIXED') || u.includes('BUYITNOW') || (u.includes('BUY') && u.includes('NOW'))) {
            return 'Buy it now';
        }
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

    let auctionCountdownTimerId = null;

    function stopAuctionCountdownTimer() {
        if (auctionCountdownTimerId != null) {
            clearInterval(auctionCountdownTimerId);
            auctionCountdownTimerId = null;
        }
    }

    function tickAuctionCountdowns() {
        document.querySelectorAll('[data-countdown-end]').forEach((el) => {
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

    function startAuctionCountdownTimer() {
        stopAuctionCountdownTimer();
        if (!document.querySelector('[data-countdown-end]')) return;
        tickAuctionCountdowns();
        auctionCountdownTimerId = setInterval(tickAuctionCountdowns, 1000);
    }

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

    function applyCarouselDotsMode(dotsRoot, mode) {
        if (!dotsRoot) return;
        const slide = mode === 'slide';
        dotsRoot.classList.toggle('is-carousel-slide', slide);
        dotsRoot.classList.toggle('is-carousel-edge', !slide);
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
            const goingNext = direction === 'next' || (direction == null && slideDelta > 0);
            track.style.transition = 'none';
            track.style.transform = goingNext ? `translateX(${step}px)` : `translateX(${-step}px)`;
            requestAnimationFrame(() => {
                track.style.transition = 'transform 0.28s ease';
                track.style.transform = 'translateX(0)';
            });
        } else {
            track.style.transition = '';
            track.style.transform = 'translateX(0)';
        }
    }

    function initCarouselsIn(root) {
        if (!root) return;
        root.querySelectorAll('[data-carousel]').forEach((carouselRoot) => {
            const strip = carouselRoot.querySelector('.car-card-carousel-strip');
            const imgs = strip ? Array.from(strip.querySelectorAll('.car-card-carousel-img')) : [];
            const count = imgs.length;
            if (count < 2) return;
            let idx = 0;
            const dotsBox = carouselRoot.querySelector('.car-card-carousel-dots');
            const show = (nextIndex, direction) => {
                idx = (nextIndex + count) % count;
                if (strip) {
                    strip.classList.remove('is-anim-left', 'is-anim-right');
                    strip.style.transform = `translate3d(-${idx * 100}%, 0, 0)`;
                    if (direction === 'next') strip.classList.add('is-anim-right');
                    else if (direction === 'prev') strip.classList.add('is-anim-left');
                }
                refreshCarouselDots(dotsBox, count, idx, direction);
                carouselRoot.dataset.slideIndex = String(idx);
            };
            carouselRoot.querySelector('.car-card-carousel-nav--prev')?.addEventListener('click', (ev) => {
                ev.preventDefault();
                ev.stopPropagation();
                show(idx - 1, 'prev');
            });
            carouselRoot.querySelector('.car-card-carousel-nav--next')?.addEventListener('click', (ev) => {
                ev.preventDefault();
                ev.stopPropagation();
                show(idx + 1, 'next');
            });
            dotsBox?.addEventListener('click', (ev) => {
                const d = ev.target.closest('.car-card-carousel-dot');
                if (!d) return;
                ev.preventDefault();
                ev.stopPropagation();
                const target = Number(d.dataset.slideTo);
                const dir = target > idx ? 'next' : target < idx ? 'prev' : null;
                show(target, dir);
            });
            if (strip) strip.style.transform = 'translate3d(0, 0, 0)';
            applyCarouselDotsMode(dotsBox, carouselDotWindow(count, 0).mode);
        });
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
                    `<img class="car-card-carousel-img" src="${attrEncode(url)}" alt="" data-slide="${i}" loading="lazy" draggable="false">`,
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

    function locationLine(car, showCountryInLocation = true) {
        const L = car.location;
        if (!L) return 'Location: —';
        const parts = [L.city, L.region];
        if (showCountryInLocation && L.country) {
            parts.push(L.country);
        }
        const filtered = parts.filter(Boolean);
        return filtered.length ? `Location: ${filtered.join(', ')}` : 'Location: —';
    }

    function specLines(car, options = {}) {
        const showCountryInLocation = options.showCountryInLocation !== false;
        const body = car.body_style || '—';
        const drive = car.drive_type || '—';
        const title = car.vehicle_title || '—';
        const mech = [car.transmission, car.engine].filter(Boolean).join(' · ');
        const mechLine = mech
            ? `<span class="car-card-spec-line">${escapeHtml(mech)}</span>`
            : '';
        return `
        <span class="car-card-spec-line">${escapeHtml(locationLine(car, showCountryInLocation))}</span>
        <span class="car-card-spec-line">${escapeHtml(body)} · ${escapeHtml(drive)}</span>
        <span class="car-card-spec-line">Title: ${escapeHtml(title)}</span>
        ${mechLine}
        <span class="car-card-spec-line">${escapeHtml(deliverySummary(car.delivery))}</span>
    `;
    }

    function carSubtitleLine(car) {
        const cond = car.condition || '—';
        return `${cond} · ${formatMileageDisplay(car)}`;
    }

    function normalizeAspectName(name) {
        return String(name).trim().toLowerCase().replace(/\s+/g, ' ');
    }

    function aspectValueByNames(aspects, names) {
        if (!Array.isArray(aspects) || !names.length) return null;
        const wanted = new Set(names.map(normalizeAspectName));
        for (const row of aspects) {
            if (!row || row.name == null || row.value == null) continue;
            if (wanted.has(normalizeAspectName(row.name))) {
                const v = String(row.value).trim();
                if (v && v !== '—') return v;
            }
        }
        return null;
    }

    function vehicleDetailValue(value) {
        if (value == null) return null;
        const s = String(value).trim();
        if (!s || s === '—') return null;
        return s;
    }

    function modalVehicleDetailsHtml(car) {
        const aspects = car.listing_aspects || [];
        const fuelMpg =
            car.fuel_city != null && car.fuel_highway != null
                ? `${car.fuel_city} / ${car.fuel_highway} mpg`
                : null;
        const fmt = listingFormatLabel(car.listing_format);
        const bodyDrive = [car.body_style, car.drive_type].filter(Boolean).join(' · ');

        const rows = [
            ['Year', car.year != null ? String(car.year) : null],
            ['Make', car.brand],
            ['Model', car.model],
            ['Sub Model', aspectValueByNames(aspects, ['Sub Model', 'SubModel'])],
            ['Trim', car.trim],
            ['Exterior Color', aspectValueByNames(aspects, ['Exterior Color'])],
            ['Interior Color', aspectValueByNames(aspects, ['Interior Color'])],
            ['Body / drive', bodyDrive || null],
            ['Number of Doors', aspectValueByNames(aspects, ['Number of Doors', 'Doors'])],
            ['Number of Cylinders', aspectValueByNames(aspects, ['Number of Cylinders', 'Cylinders'])],
            ['Engine', car.engine],
            ['Transmission', car.transmission],
            ['Fuel type', car.fuel_type],
            ['Fuel (city / hwy)', fuelMpg],
            ['Condition', car.condition],
            ['Mileage', formatMileageDisplay(car)],
            ['For Sale By', aspectValueByNames(aspects, ['For Sale By'])],
            ['Seller', car.seller_username],
            ['Warranty', aspectValueByNames(aspects, ['Warranty'])],
            ['Listing type', fmt && fmt !== '—' ? fmt : null],
            ['Title', car.vehicle_title],
            ['VIN', car.vin],
            ['Location', locationLine(car, true).replace(/^Location:\s*/, '')],
            ['Delivery', deliverySummary(car.delivery).replace(/^Delivery:\s*/, '')],
        ].filter(([, value]) => vehicleDetailValue(value));

        if (rows.length === 0) return '';
        const items = rows
            .map(
                ([label, value]) =>
                    `<div class="car-detail-spec-row"><span class="car-detail-spec-label">${escapeHtml(label)}</span><span class="car-detail-spec-value">${escapeHtml(String(value))}</span></div>`,
            )
            .join('');
        return `<section class="car-detail-vehicle-details"><h2 class="car-detail-section-title">Vehicle details</h2><div class="car-detail-spec-grid">${items}</div></section>`;
    }

    function listingLinkButtonHtml(car, className = 'car-detail-ebay-btn') {
        const url = getListingUrl(car);
        if (!url) return '';
        return `<a class="${className}" href="${attrEncode(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(listingLinkLabel(car))}</a>`;
    }

    function watchHeartButtonHtml(car, isWatched, extraAttrs = '') {
        const label = isWatched ? 'Remove from watchlist' : 'Add to watchlist';
        const watchedCls = isWatched ? ' is-watched' : '';
        const extra = extraAttrs ? ` ${extraAttrs}` : '';
        return `<button type="button" class="car-card-watch-btn${watchedCls}" data-car-id="${escapeAttr(String(car.id))}"${extra} aria-label="${escapeAttr(label)}" aria-pressed="${isWatched ? 'true' : 'false'}">
            <svg class="car-card-watch-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" fill="currentColor"/>
            </svg>
        </button>`;
    }

    function buildCarCardHtml(car, options = {}) {
        const showWatchButton = Boolean(options.showWatchButton);
        const isWatched = Boolean(options.isWatched);
        const listingLinkClass =
            options.listingLinkClass || 'car-card-listing-link car-card-listing-link--footer';
        const specOptions = {
            showCountryInLocation: options.showCountryInLocation !== false,
        };
        const watchBtn = showWatchButton ? watchHeartButtonHtml(car, isWatched) : '';

        const displayTitle =
            (typeof car.listing_title === 'string' && car.listing_title.trim()) ||
            `${car.brand || ''} ${car.model || ''}`.trim() ||
            'Listing';
        return `
            <article class="car-card" data-car-id="${car.id}">
                <div class="car-card-media">
                    ${carouselHtml(car)}
                </div>
                <div class="car-card-body">
                    <div class="car-card-title-row">
                        <div class="car-card-title-year-col">
                            <span class="car-year-pill">${car.year != null ? escapeHtml(String(car.year)) : '—'}</span>
                        </div>
                        <span class="car-card-title-vrule" aria-hidden="true"></span>
                        <div class="car-card-title-main">
                            <h3 class="car-model">${escapeHtml(displayTitle)}</h3>
                            <p class="car-card-subtitle">${escapeHtml(carSubtitleLine(car))}</p>
                        </div>
                        ${watchBtn}
                    </div>
                    <div class="car-card-divider" aria-hidden="true"></div>
                    <div class="car-card-specs">${specLines(car, specOptions)}</div>
                    <div class="car-card-divider" aria-hidden="true"></div>
                    <div class="car-card-footer">
                        <div class="car-card-footer-start">
                            ${priceBlockHtml(car)}
                            ${listingLinkHtml(car, listingLinkClass)}
                        </div>
                        ${metricsBlockHtml(car)}
                    </div>
                </div>
            </article>`;
    }

    window.Css360Listing = {
        escapeHtml,
        escapeAttr,
        formatMoney,
        formatPriceShort,
        formatMileageDisplay,
        isPriceKnown,
        shouldShowEconomics,
        formatRoiDisplay,
        formatProfitDisplay,
        metricsBlockHeatStyle,
        isRoiPreliminary,
        roiPreliminaryBadgeHtml,
        calculateHeatmap,
        calculateHeatmapBorder,
        metricsBlockHtml,
        formatResaleMethodLabel,
        formatResaleConfidence,
        resaleEstimateMetaHtml,
        resaleEstimateDetailHtml,
        priceBlockHtml,
        listingLinkHtml,
        specLines,
        carSubtitleLine,
        carouselHtml,
        carouselDotWindow,
        carouselDotsButtonsHtml,
        carouselDotsMarkup,
        modalVehicleDetailsHtml,
        modalPurchasePriceHtml,
        LISTING_FORMAT_LABELS,
        DELIVERY_CHIPS,
        buildCarCardHtml,
        listingLinkButtonHtml,
        watchHeartButtonHtml,
        refreshCarouselDots,
        initCarouselsIn,
        startAuctionCountdownTimer,
        stopAuctionCountdownTimer,
    };
}());
