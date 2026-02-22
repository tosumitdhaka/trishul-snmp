/**
 * js/modules/utils.js
 * ~~~~~~~~~~~~~~~~~~~
 * Shared utility functions used across all Trishul modules.
 * Loaded FIRST (before ws-client.js and all module scripts) so every
 * module can call TrishulUtils.* without any import ceremony.
 */
window.TrishulUtils = {

    /**
     * Convert an ISO timestamp string OR Unix timestamp to a human-readable
     * relative time string.
     * Returns strings like: 'just now', '34s ago', '5m ago', '2h ago',
     * '3d ago', or a locale date string for anything older than a week.
     *
     * Edge cases handled:
     *   null / undefined / ''       → '--'
     *   Unix epoch (0 ms)           → '--'  (backend returns 0 for "never received")
     *   NaN / unparseable           → '--'
     *   Unix seconds as number      → auto-detected and converted to ms
     *     (backend may send integer seconds, e.g. 1737000000, rather than ms;
     *      new Date(1737000000) in JS = Jan 21 1970 because JS expects ms)
     *
     * Detection rule:
     *   number < 1e10  → Unix seconds  (current epoch ~1.74e9)
     *   number ≥ 1e10  → Unix milliseconds
     *   string          → passed to new Date() as-is (ISO 8601 etc.)
     *
     * @param {string|number|null} dateString  ISO 8601 timestamp, Unix seconds,
     *                                         Unix ms, or null
     * @returns {string}
     */
    formatRelativeTime: function(dateString) {
        if (dateString == null || dateString === '') return '--';
        try {
            var date;
            if (typeof dateString === 'number') {
                // Distinguish Unix seconds from Unix milliseconds.
                // Current time in seconds is ~1.74e9; in ms ~1.74e12.
                // Threshold 1e10 safely separates them for dates until year 2286.
                date = dateString < 1e10 ? new Date(dateString * 1000)
                                         : new Date(dateString);
            } else {
                date = new Date(dateString);
            }

            var timeMs = date.getTime();

            // Treat unparseable dates or Unix epoch as "never"
            if (isNaN(timeMs) || timeMs < 1000) return '--';

            var now     = new Date();
            var diffMs  = now - date;
            var diffSec = Math.floor(diffMs / 1000);
            var diffMin = Math.floor(diffSec / 60);
            var diffHr  = Math.floor(diffMin / 60);
            var diffDay = Math.floor(diffHr  / 24);

            if (diffSec < 5)   return 'just now';
            if (diffSec < 60)  return diffSec + 's ago';
            if (diffMin < 60)  return diffMin + 'm ago';
            if (diffHr  < 24)  return diffHr  + 'h ago';
            if (diffDay < 7)   return diffDay  + 'd ago';
            return date.toLocaleDateString();
        } catch (_) {
            return '--';
        }
    },

    /**
     * Convert a duration in whole seconds to a compact human-readable string.
     * Examples:
     *   45      → '45s'
     *   125     → '2m 5s'
     *   3600    → '1h'
     *   3900    → '1h 5m'
     *   90000   → '1d 1h'
     *   86400   → '1d'
     *
     * @param {number|null} seconds  Duration in seconds (null/undefined → '--')
     * @returns {string}
     */
    formatUptime: function(seconds) {
        if (seconds == null || seconds < 0) return '--';
        seconds = Math.floor(seconds);
        if (seconds < 60) {
            return seconds + 's';
        }
        if (seconds < 3600) {
            var m = Math.floor(seconds / 60);
            var s = seconds % 60;
            return s > 0 ? (m + 'm ' + s + 's') : (m + 'm');
        }
        if (seconds < 86400) {
            var h = Math.floor(seconds / 3600);
            var m = Math.floor((seconds % 3600) / 60);
            return m > 0 ? (h + 'h ' + m + 'm') : (h + 'h');
        }
        var d = Math.floor(seconds / 86400);
        var h = Math.floor((seconds % 86400) / 3600);
        return h > 0 ? (d + 'd ' + h + 'h') : (d + 'd');
    },

    /**
     * Show a dismissible toast-style notification banner at top-right.
     * Auto-removes after `duration` ms.
     *
     * Replaces the per-module showNotification copies in walker.js,
     * mibs.js, and browser.js — call as TrishulUtils.showNotification(...).
     *
     * @param {string} message   Text to display (HTML is allowed)
     * @param {string} type      'info' | 'success' | 'error' | 'warning'
     * @param {number} duration  Auto-dismiss delay in ms (default 3000)
     */
    showNotification: function(message, type, duration) {
        type     = type     || 'info';
        duration = duration || 3000;

        var icon = 'fa-info-circle';
        var cls  = 'alert-info';

        if      (type === 'success') { icon = 'fa-check-circle';         cls = 'alert-success'; }
        else if (type === 'error')   { icon = 'fa-exclamation-circle';   cls = 'alert-danger';  }
        else if (type === 'warning') { icon = 'fa-exclamation-triangle'; cls = 'alert-warning'; }

        var banner = document.createElement('div');
        banner.className = 'alert ' + cls + ' alert-dismissible fade show position-fixed';
        banner.style.cssText = 'top: 80px; right: 20px; z-index: 9999; min-width: 300px; max-width: 420px;';
        banner.innerHTML =
            '<i class="fas ' + icon + ' me-2"></i>' + message +
            '<button type="button" class="btn-close" data-bs-dismiss="alert"></button>';
        document.body.appendChild(banner);
        setTimeout(function() { if (banner.parentNode) banner.remove(); }, duration);
    },
};
