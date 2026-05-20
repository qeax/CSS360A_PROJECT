/**
 * Profile page — minimal account summary from /api/auth/me.
 */

function renderProfilePage(me) {
    const email = me.email || '';
    const displayName = (me.display_name && me.display_name.trim())
        || displayNameFromEmail(email);

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

document.addEventListener('DOMContentLoaded', async () => {
    initAppShell();
    const me = await requireAuth();
    if (!me) return;
    renderProfilePage(me);
});
