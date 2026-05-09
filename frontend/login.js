/**
 * Login page: redirects authenticated users to the dashboard; surfaces OAuth errors from the query string.
 */

const ERROR_MESSAGES = {
    oauth_error: 'Sign-in was cancelled or could not be completed. Please try again.',
    invalid_request: 'Invalid sign-in request. Please start again from this page.',
    invalid_state: 'Your session expired before sign-in finished. Please try again.',
    no_id_token: 'Sign-in did not return an identity token. Please try again.',
    wrong_tenant: 'This account is not allowed for this application.',
    missing_identity: 'Your account profile did not include an email. Contact IT if this persists.',
    email_not_allowed: 'This email domain is not authorized to access this application.',
    sign_in_failed: 'Sign-in failed. Please try again or contact support.',
};

function initTheme() {
    if (localStorage.getItem('theme') === 'light') {
        document.body.classList.add('light-theme');
    }
}

function showErrorFromQuery() {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('error');
    if (!code) return;
    const el = document.getElementById('loginError');
    if (!el) return;
    const msg = ERROR_MESSAGES[code] || ERROR_MESSAGES.sign_in_failed;
    el.textContent = msg;
    el.hidden = false;
}

async function redirectIfAuthenticated() {
    try {
        const res = await fetch('/api/auth/me', { credentials: 'include' });
        if (res.ok) {
            window.location.replace('index.html');
        }
    } catch {
        // Stay on login when the API is unreachable
    }
}

document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    showErrorFromQuery();
    redirectIfAuthenticated();
});
