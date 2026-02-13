/**
 * Theme Toggle Component
 * Button to switch between light/dark modes
 */

import { Component, html } from '../core/component.js';

export class ThemeToggle extends Component {
    constructor(container, props = {}, store = null, themeManager = null) {
        super(container, {
            showLabel: true,
            size: 'md', // 'sm', 'md', 'lg'
            className: '',
            ...props
        }, store);
        
        this.themeManager = themeManager;
        this.state = {
            theme: this.themeManager ? this.themeManager.getEffectiveTheme() : 'light'
        };
    }

    render() {
        const { showLabel, size, className } = this.props;
        const { theme } = this.state;
        
        const sizeClass = size === 'sm' ? 'btn-sm' : size === 'lg' ? 'btn-lg' : '';
        const icon = theme === 'dark' ? 'fa-moon' : 'fa-sun';
        const label = theme === 'dark' ? 'Dark' : 'Light';
        
        return html`
            <button class="btn btn-outline-secondary ${sizeClass} ${className}" 
                    data-theme-toggle
                    title="Toggle ${theme === 'dark' ? 'light' : 'dark'} mode"
                    aria-label="Toggle theme">
                <i class="fas ${icon}"></i>
                ${showLabel ? html`<span class="ms-2">${label}</span>` : ''}
            </button>
        `;
    }

    async mounted() {
        // Handle toggle click
        this.on('click', '[data-theme-toggle]', () => {
            if (this.themeManager) {
                this.themeManager.toggle();
                this.setState({ theme: this.themeManager.getEffectiveTheme() });
            }
        });
        
        // Listen for theme changes from other sources
        window.addEventListener('theme:changed', (e) => {
            this.setState({ theme: e.detail.theme });
        });
    }
}
