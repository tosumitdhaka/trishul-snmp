/**
 * Theme Manager
 * Handles dark/light mode with persistence
 */

export class ThemeManager {
    constructor(store) {
        this.store = store;
        this.themes = ['light', 'dark', 'auto'];
        this.currentTheme = this.store.get('theme') || 'auto';
        
        console.log('[Theme] ThemeManager initialized');
    }

    /**
     * Initialize theme system
     */
    init() {
        // Apply saved theme
        this.applyTheme(this.currentTheme);
        
        // Listen for system theme changes
        if (window.matchMedia) {
            window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
                if (this.currentTheme === 'auto') {
                    this.applySystemTheme();
                }
            });
        }
        
        console.log('[Theme] Theme system initialized with:', this.currentTheme);
    }

    /**
     * Get current theme
     */
    getTheme() {
        return this.currentTheme;
    }

    /**
     * Get effective theme (resolves 'auto' to light/dark)
     */
    getEffectiveTheme() {
        if (this.currentTheme === 'auto') {
            return this.getSystemTheme();
        }
        return this.currentTheme;
    }

    /**
     * Get system theme preference
     */
    getSystemTheme() {
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
            return 'dark';
        }
        return 'light';
    }

    /**
     * Set theme
     */
    setTheme(theme) {
        if (!this.themes.includes(theme)) {
            console.error('[Theme] Invalid theme:', theme);
            return;
        }
        
        this.currentTheme = theme;
        this.store.set('theme', theme);
        this.applyTheme(theme);
        
        console.log('[Theme] Theme changed to:', theme);
    }

    /**
     * Toggle between light and dark
     */
    toggle() {
        const effective = this.getEffectiveTheme();
        const newTheme = effective === 'dark' ? 'light' : 'dark';
        this.setTheme(newTheme);
    }

    /**
     * Apply theme to document
     */
    applyTheme(theme) {
        const effectiveTheme = theme === 'auto' ? this.getSystemTheme() : theme;
        
        // Remove all theme classes
        document.documentElement.classList.remove('theme-light', 'theme-dark');
        
        // Add new theme class
        document.documentElement.classList.add(`theme-${effectiveTheme}`);
        
        // Set data attribute for CSS targeting
        document.documentElement.setAttribute('data-theme', effectiveTheme);
        
        // Update Bootstrap color mode (if supported)
        if (document.documentElement.hasAttribute('data-bs-theme')) {
            document.documentElement.setAttribute('data-bs-theme', effectiveTheme);
        }
        
        // Emit event
        window.dispatchEvent(new CustomEvent('theme:changed', {
            detail: { theme: effectiveTheme }
        }));
    }

    /**
     * Apply system theme
     */
    applySystemTheme() {
        const systemTheme = this.getSystemTheme();
        this.applyTheme(systemTheme);
    }
}
