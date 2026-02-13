/**
 * Trishul SNMP - Main Application Entry Point
 * Modern ES6 Module-based Architecture
 */

import { Router } from './core/router.js';
import { AuthManager } from './core/auth.js';
import { ApiClient } from './core/api.js';

// Import modules - These will be converted to proper ES6 classes step by step
// For now, we'll keep compatibility with existing window.XxxModule pattern

/**
 * Main Application Class
 */
class App {
    constructor() {
        this.router = new Router();
        this.auth = new AuthManager();
        this.api = new ApiClient();
        
        // Make available globally for debugging and compatibility
        window.app = this;
        
        console.log('[App] Trishul SNMP initializing...');
    }

    /**
     * Initialize application
     */
    async init() {
        console.log('[App] Starting initialization...');
        
        // Setup routes
        this.setupRoutes();
        
        // Setup global event listeners
        this.setupEventListeners();
        
        // Check authentication
        if (this.auth.isAuthenticated()) {
            const verification = await this.auth.verify();
            
            if (verification.valid) {
                console.log('[App] Token valid, showing app');
                this.updateUserUI(verification.user);
                await this.showApp();
            } else {
                console.log('[App] Token invalid, showing login');
                this.showLogin();
            }
        } else {
            console.log('[App] Not authenticated, showing login');
            this.showLogin();
        }
    }

    /**
     * Register routes with their module classes
     * Using temporary HTML loading until modules are fully converted
     */
    setupRoutes() {
        const container = document.getElementById('main-content');
        
        // Temporary route handler that loads HTML and initializes old modules
        const createModuleWrapper = (moduleName) => {
            return class {
                constructor(container) {
                    this.container = container;
                    this.moduleName = moduleName;
                }
                
                async init() {
                    // Load HTML
                    const response = await fetch(`${this.moduleName}.html`);
                    if (!response.ok) throw new Error('Module not found');
                    const html = await response.text();
                    this.container.innerHTML = html;
                    
                    // Initialize old module if exists
                    const capitalizedName = this.moduleName.charAt(0).toUpperCase() + this.moduleName.slice(1);
                    const oldModule = window[`${capitalizedName}Module`];
                    if (oldModule && typeof oldModule.init === 'function') {
                        oldModule.init();
                    }
                }
                
                destroy() {
                    const capitalizedName = this.moduleName.charAt(0).toUpperCase() + this.moduleName.slice(1);
                    const oldModule = window[`${capitalizedName}Module`];
                    if (oldModule && typeof oldModule.destroy === 'function') {
                        oldModule.destroy();
                    }
                }
            };
        };
        
        this.router
            .setContainer(container)
            .register('dashboard', createModuleWrapper('dashboard'))
            .register('simulator', createModuleWrapper('simulator'))
            .register('walker', createModuleWrapper('walker'))
            .register('traps', createModuleWrapper('traps'))
            .register('browser', createModuleWrapper('browser'))
            .register('mibs', createModuleWrapper('mibs'))
            .register('settings', createModuleWrapper('settings'));
        
        console.log('[App] Routes registered');
    }

    /**
     * Setup global event listeners
     */
    setupEventListeners() {
        // Hash change for routing
        window.addEventListener('hashchange', () => {
            this.handleRoute();
        });

        // Auth events
        window.addEventListener('auth:unauthorized', () => {
            console.log('[App] Unauthorized event received');
            this.logout();
        });

        // Sidebar toggle
        const sidebarToggle = document.getElementById('sidebarToggle');
        if (sidebarToggle) {
            sidebarToggle.addEventListener('click', (e) => {
                e.preventDefault();
                document.body.classList.toggle('sb-sidenav-toggled');
            });
        }

        // Login form
        const loginForm = document.getElementById('login-form');
        if (loginForm) {
            loginForm.addEventListener('submit', (e) => this.handleLogin(e));
        }

        console.log('[App] Event listeners setup');
    }

    /**
     * Handle route changes
     */
    async handleRoute() {
        const route = this.router.getCurrentRoute();
        console.log('[App] Route changed:', route);
        
        await this.router.navigate(route);
        this.updateActiveNavItem(route);
    }

    /**
     * Update active navigation item
     */
    updateActiveNavItem(route) {
        document.querySelectorAll('.list-group-item').forEach(el => {
            const href = el.getAttribute('href');
            el.classList.toggle('active', href === `#${route}`);
        });
    }

    /**
     * Handle login form submission
     */
    async handleLogin(event) {
        event.preventDefault();
        
        const username = document.getElementById('login-user').value;
        const password = document.getElementById('login-pass').value;
        const submitBtn = document.getElementById('login-btn');
        const errorDiv = document.getElementById('login-error');
        
        // Disable form
        submitBtn.disabled = true;
        errorDiv.classList.add('d-none');
        
        try {
            const result = await this.auth.login(username, password);
            
            if (result.success) {
                console.log('[App] Login successful');
                this.updateUserUI(result.user);
                await this.showApp();
            } else {
                console.error('[App] Login failed:', result.error);
                errorDiv.textContent = result.error;
                errorDiv.classList.remove('d-none');
            }
        } catch (error) {
            console.error('[App] Login error:', error);
            errorDiv.textContent = 'An unexpected error occurred';
            errorDiv.classList.remove('d-none');
        } finally {
            submitBtn.disabled = false;
        }
    }

    /**
     * Show application (hide login)
     */
    async showApp() {
        const loginScreen = document.getElementById('login-screen');
        const wrapper = document.getElementById('wrapper');
        
        if (loginScreen) {
            loginScreen.style.display = 'none';
        }
        
        if (wrapper) {
            wrapper.style.display = 'flex';
        }
        
        // Load app metadata
        await this.loadAppMetadata();
        
        // Start periodic health check
        this.startHealthCheck();
        
        // Navigate to current route
        await this.handleRoute();
        
        console.log('[App] Application shown');
    }

    /**
     * Show login screen (hide app)
     */
    showLogin() {
        const loginScreen = document.getElementById('login-screen');
        const wrapper = document.getElementById('wrapper');
        
        if (loginScreen) {
            loginScreen.style.display = 'flex';
        }
        
        if (wrapper) {
            wrapper.style.display = 'none';
        }
        
        console.log('[App] Login screen shown');
    }

    /**
     * Update user info in UI
     */
    updateUserUI(username) {
        const userNameEl = document.getElementById('nav-user-name');
        if (userNameEl) {
            userNameEl.textContent = username || 'User';
        }
    }

    /**
     * Load application metadata
     */
    async loadAppMetadata() {
        const versionEl = document.getElementById('app-version');
        const badge = document.getElementById('backend-status');
        
        try {
            const data = await this.api.get('/meta');
            
            if (badge) {
                badge.className = 'badge bg-success';
                badge.textContent = 'Online';
            }
            
            if (versionEl) {
                versionEl.textContent = `v${data.version}`;
                versionEl.title = `${data.name} v${data.version}`;
            }
            
            document.title = data.name;
            
            window.AppMetadata = data;
            
            console.log(`[App] 🔱 ${data.name} v${data.version} loaded`);
            
        } catch (error) {
            console.error('[App] Failed to load metadata:', error);
            
            if (badge) {
                badge.className = 'badge bg-danger';
                badge.textContent = 'Offline';
            }
            
            if (versionEl) {
                versionEl.textContent = 'Offline';
                versionEl.style.color = '#ef4444';
            }
        }
    }

    /**
     * Start periodic backend health check
     */
    startHealthCheck() {
        // Clear any existing interval
        if (this.healthCheckInterval) {
            clearInterval(this.healthCheckInterval);
        }
        
        // Check every 60 seconds
        this.healthCheckInterval = setInterval(async () => {
            await this.checkBackendHealth();
        }, 60000);
    }

    /**
     * Check backend health
     */
    async checkBackendHealth() {
        const badge = document.getElementById('backend-status');
        
        try {
            const data = await this.api.get('/meta');
            
            if (badge && !badge.classList.contains('bg-success')) {
                badge.className = 'badge bg-success';
                badge.textContent = 'Online';
                console.log('[App] Backend is back online');
            }
            
        } catch (error) {
            if (badge && badge.classList.contains('bg-success')) {
                badge.className = 'badge bg-danger';
                badge.textContent = 'Offline';
                console.error('[App] Backend went offline');
            }
        }
    }

    /**
     * Logout user
     */
    async logout() {
        console.log('[App] Logging out...');
        
        // Stop health check
        if (this.healthCheckInterval) {
            clearInterval(this.healthCheckInterval);
        }
        
        await this.auth.logout();
        window.location.reload();
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    console.log('[App] DOM loaded, initializing...');
    
    const app = new App();
    app.init().catch(error => {
        console.error('[App] Initialization failed:', error);
    });
});

// Make logout function global for HTML onclick handlers
window.logout = () => {
    if (window.app) {
        window.app.logout();
    }
};

// Maintain backward compatibility with old login handler
window.handleLogin = (e) => {
    if (window.app) {
        window.app.handleLogin(e);
    }
};
