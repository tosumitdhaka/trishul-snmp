/**
 * Theme Manager
 * Handles dark/light mode switching with persistence
 */

export class ThemeManager {
    constructor(store) {
        this.store = store;
        this.currentTheme = this.getStoredTheme() || 'light';
        
        console.log('[Theme] ThemeManager initialized');
    }

    /**
     * Initialize theme manager
     */
    init() {
        // Apply stored theme
        this.applyTheme(this.currentTheme);
        
        // Listen for system theme changes
        this.watchSystemTheme();
        
        // Update store
        if (this.store) {
            this.store.set('theme', this.currentTheme);
        }
        
        console.log(`[Theme] Applied theme: ${this.currentTheme}`);
    }

    /**
     * Get stored theme from localStorage
     */
    getStoredTheme() {
        return localStorage.getItem('theme');
    }

    /**
     * Store theme in localStorage
     */
    storeTheme(theme) {
        localStorage.setItem('theme', theme);
    }

    /**
     * Get system preferred theme
     */
    getSystemTheme() {
        if (window.matchMedia) {
            return window.matchMedia('(prefers-color-scheme: dark)').matches 
                ? 'dark' 
                : 'light';
        }
        return 'light';
    }

    /**
     * Watch for system theme changes
     */
    watchSystemTheme() {
        if (!window.matchMedia) return;
        
        const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
        
        mediaQuery.addEventListener('change', (e) => {
            // Only auto-switch if user hasn't manually set a preference
            if (!this.getStoredTheme()) {
                const newTheme = e.matches ? 'dark' : 'light';
                this.setTheme(newTheme);
                console.log(`[Theme] System theme changed to: ${newTheme}`);
            }
        });
    }

    /**
     * Apply theme to document
     */
    applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        this.currentTheme = theme;
        
        // Update meta theme-color for mobile browsers
        const metaThemeColor = document.querySelector('meta[name="theme-color"]');
        if (metaThemeColor) {
            metaThemeColor.setAttribute(
                'content', 
                theme === 'dark' ? '#1a1d23' : '#ffffff'
            );
        }
    }

    /**
     * Set theme and persist
     */
    setTheme(theme) {
        this.applyTheme(theme);
        this.storeTheme(theme);
        
        if (this.store) {
            this.store.set('theme', theme);
        }
        
        console.log(`[Theme] Theme changed to: ${theme}`);
        
        // Emit event for other components
        window.dispatchEvent(new CustomEvent('theme:changed', { 
            detail: { theme } 
        }));
    }

    /**
     * Toggle between light and dark
     */
    toggle() {
        const newTheme = this.currentTheme === 'light' ? 'dark' : 'light';
        this.setTheme(newTheme);
        return newTheme;
    }

    /**
     * Get current theme
     */
    getTheme() {
        return this.currentTheme;
    }

    /**
     * Check if dark mode is active
     */
    isDark() {
        return this.currentTheme === 'dark';
    }

    /**
     * Check if light mode is active
     */
    isLight() {
        return this.currentTheme === 'light';
    }
}

// Make available globally
window.ThemeManager = ThemeManager;
