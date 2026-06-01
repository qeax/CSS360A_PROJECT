(async function initSettingsPage() {
    initAppShell();
    const me = await requireAuth();
    if (!me) return;

    const toggle = document.getElementById('showListingJsonDebug');
    const saveBtn = document.getElementById('saveSettingsBtn');
    const savedMsg = document.getElementById('settingsSavedMsg');
    const settings = getSettings();
    if (toggle) toggle.checked = settings.showListingJsonDebug;

    saveBtn?.addEventListener('click', () => {
        saveSettings({ showListingJsonDebug: Boolean(toggle?.checked) });
        if (savedMsg) {
            savedMsg.hidden = false;
            window.setTimeout(() => {
                savedMsg.hidden = true;
            }, 2000);
        }
    });
})();
