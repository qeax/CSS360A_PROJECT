(async function initSettingsPage() {
    initAppShell();

    const me = await requireAuth();
    if (!me) return;

    setNotificationsBadge(me.notifications_unread_count);
    await runWatchCheckIfDue();

    const jsonDebugToggle = document.getElementById('showListingJsonDebug');
    const deleteBtnToggle = document.getElementById('showDeleteCarButton');
    const listingPageToggle = document.getElementById('listingDetailPageMode');
    const settings = getSettings();

    if (jsonDebugToggle) jsonDebugToggle.checked = settings.showListingJsonDebug;
    if (deleteBtnToggle) deleteBtnToggle.checked = settings.showDeleteCarButton;
    if (listingPageToggle) listingPageToggle.checked = settings.listingDetailMode !== 'modal';

    jsonDebugToggle?.addEventListener('change', () => {
        saveSettings({ showListingJsonDebug: Boolean(jsonDebugToggle.checked) });
    });

    deleteBtnToggle?.addEventListener('change', () => {
        saveSettings({ showDeleteCarButton: Boolean(deleteBtnToggle.checked) });
    });

    listingPageToggle?.addEventListener('change', () => {
        saveSettings({
            listingDetailMode: listingPageToggle.checked ? 'page' : 'modal',
        });
    });

    document.querySelectorAll('.settings-toggle').forEach((label) => {
        label.addEventListener('mousedown', (e) => e.preventDefault());
    });

    const testBtn = document.getElementById('sendTestNotificationBtn');
    testBtn?.addEventListener('click', async () => {
        testBtn.disabled = true;
        try {
            const res = await fetch('/api/notifications/test-preview', {
                method: 'POST',
                credentials: 'include',
            });
            if (!res.ok) {
                alert('Could not send test notification.');
                return;
            }
            const data = await res.json();
            if (typeof window.injectEphemeralNotification === 'function' && data.item) {
                window.injectEphemeralNotification(data.item);
            }
        } catch (_) {
            alert('Could not send test notification.');
        } finally {
            testBtn.disabled = false;
        }
    });
})();
