(async function initSettingsPage() {
    initAppShell();
    const me = await requireAuth();
    if (!me) return;

    const jsonDebugToggle = document.getElementById('showListingJsonDebug');
    const deleteBtnToggle = document.getElementById('showDeleteCarButton');
    const settings = getSettings();

    if (jsonDebugToggle) jsonDebugToggle.checked = settings.showListingJsonDebug;
    if (deleteBtnToggle) deleteBtnToggle.checked = settings.showDeleteCarButton;

    jsonDebugToggle?.addEventListener('change', () => {
        saveSettings({ showListingJsonDebug: Boolean(jsonDebugToggle.checked) });
    });
    deleteBtnToggle?.addEventListener('change', () => {
        saveSettings({ showDeleteCarButton: Boolean(deleteBtnToggle.checked) });
    });

    document.querySelectorAll('.settings-toggle').forEach((label) => {
        label.addEventListener('mousedown', (e) => e.preventDefault());
    });
})();
