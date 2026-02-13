/**
 * Theme Manager
 * Handles dark/light mode with persistence
 */

export class ThemeManager {
    constructor(store) {
        this.store = store;
        this.themes = ['light', 'dark', 'auto'];
        this.currentTheme = this.loadTheme();
        
        console.log('[Theme] ThemeManager initialized');
    }

    /**
     * Initialize theme system
     */
    init() {
        // Set initial theme
        this.applyTheme(this.currentTheme);
        
        // Listen for system theme changes
        if (window.matchMedia) {
            window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
                if (this.currentTheme === 'auto') {
                    this.applyTheme('auto');
                }
            });
        }
        
        console.log('[Theme] Theme system initialized:', this.currentTheme);
    }

    /**
     * Load theme from storage
     */
    loadTheme() {
        const stored = localStorage.getItem('theme');
        return stored && this.themes.includes(stored) ? stored : 'light';
    }

    /**
     * Save theme to storage
     */
    saveTheme(theme) {
        localStorage.setItem('theme', theme);
    }

    /**
     * Get effective theme (resolve 'auto' to actual theme)
     */
    getEffectiveTheme() {
        if (this.currentTheme === 'auto') {
            if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
                return 'dark';
            }
            return 'light';
        }
        return this.currentTheme;
    }

    /**
     * Apply theme to document
     */
    applyTheme(theme) {
        this.currentTheme = theme;
        const effectiveTheme = this.getEffectiveTheme();
        
        // Update document
        document.documentElement.setAttribute('data-theme', effectiveTheme);
        document.body.classList.remove('light-theme', 'dark-theme');
        document.body.classList.add(`${effectiveTheme}-theme`);
        
        // Update store
        if (this.store) {
            this.store.set('theme', theme);
            this.store.set('effectiveTheme', effectiveTheme);
        }
        
        // Save to storage
        this.saveTheme(theme);
        
        // Emit event
        window.dispatchEvent(new CustomEvent('theme:changed', {
            detail: { theme, effectiveTheme }
        }));
        
        console.log('[Theme] Applied:', theme, '->', effectiveTheme);
    }

    /**
     * Toggle between light and dark
     */
    toggle() {
        const current = this.getEffectiveTheme();
        const next = current === 'light' ? 'dark' : 'light';
        this.applyTheme(next);
    }

    /**
     * Set specific theme
     */
    setTheme(theme) {
        if (!this.themes.includes(theme)) {
            console.warn('[Theme] Invalid theme:', theme);
            return;
        }
        this.applyTheme(theme);
    }

    /**
     * Get current theme
     */
    getTheme() {
        return this.currentTheme;
    }
}

/**
 * Theme toggle component
 */
export function createThemeToggle(themeManager) {
    const toggle = document.createElement('button');
    toggle.className = 'btn btn-link text-decoration-none theme-toggle';
    toggle.setAttribute('aria-label', 'Toggle theme');
    toggle.title = 'Toggle dark mode';
    
    const updateIcon = () => {
        const theme = themeManager.getEffectiveTheme();
        const icon = theme === 'dark' ? 'fa-sun' : 'fa-moon';
        toggle.innerHTML = `<i class="fas ${icon}"></i>`;
    };
    
    updateIcon();
    
    toggle.addEventListener('click', () => {
        themeManager.toggle();
        updateIcon();
    });
    
    window.addEventListener('theme:changed', updateIcon);
    
    return toggle;
}
