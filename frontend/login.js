/**
 * Login page — stub auth until backend accounts exist.
 * Must match AUTH_STORAGE_KEY / AUTH_STORAGE_VALUE in script.js.
 */
const AUTH_STORAGE_KEY = 'css360_authenticated';
const AUTH_STORAGE_VALUE = '1';

function initTheme() {
    if (localStorage.getItem('theme') === 'light') {
        document.body.classList.add('light-theme');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    document.getElementById('loginForm').addEventListener('submit', (e) => {
        e.preventDefault();
        localStorage.setItem(AUTH_STORAGE_KEY, AUTH_STORAGE_VALUE);
        window.location.href = 'index.html';
    });
});
