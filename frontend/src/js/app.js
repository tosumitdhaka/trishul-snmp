/**
 * Trishul SNMP - Main Application Entry Point
 * Modern ES6 Module-based Architecture with Reactive State Management
 */

import { Router } from './core/router.js';
import { AuthManager } from './core/auth.js';
import { ApiClient } from './core/api.js';
import { createAppStore } from './core/store.js';
import { ThemeManager, createThemeToggle } from './core/theme.js';
import { Toast } from './components/Toast.js';

// ==================== Fetch Interceptor (Backward Compatibility) ====================
// This interceptor automatically injects auth tokens into ALL fetch requests
// Required for legacy modules (dashboard.js, simulator.js, etc.) that make direct fetch() calls
// TODO: Remove this once all modules are migrated to use ApiClient

const originalFetch = window.fetch;
window.fetch = async function(url, options = {}) {
    const token = sessionStorage.getItem('snmp_token');
    
    if (token) {
        if (!options.headers) {
            options.headers = {};
        }
        
        if (options.headers instanceof Headers) {
            options.headers.append('X-Auth-Token', token);
        } else {
            options.headers['X-Auth-Token'] = token;
        }
    }

    const response = await originalFetch(url, options);
    
    // Trigger logout on 401 (except for login/logout endpoints)
    if (response.status === 401 && !url.includes('/login') && !url.includes('/logout')) {
        console.warn('[Fetch Interceptor] 401 Unauthorized - triggering logout');
        // Only trigger if we're currently authenticated
        if (window.app && window.app.store.get('isAuthenticated')) {
            window.dispatchEvent(new CustomEvent('auth:unauthorized'));
        }
    }

    return response;
};

console.log('[App] Fetch interceptor installed for backward compatibility');

/**
 * Main Application Class
 */
class App {
    constructor() {
        // Initialize store first
        this.store = createAppStore();
        
        // Initialize core modules with store
        this.router = new Router();
        this.auth = new AuthManager(this.store);
        this.api = new ApiClient();
        this.theme = new ThemeManager(this.store);
        
        // Track if we're already logging out to prevent loops
        this.isLoggingOut = false;
        
        // Subscribe to state changes for reactive UI
        this.setupStateSubscriptions();
        
        // Make available globally for debugging and compatibility
        window.app = this;
        
        console.log('[App] Trishul SNMP initializing...');
    }

    /**
     * Setup reactive subscriptions to state changes
     */
    setupStateSubscriptions() {
        // React to view changes (login <-> app)
        this.store.subscribe('currentView', (view) => {
            console.log('[App] View changed to:', view);
            this.renderView(view);
        });

        // React to route changes
        this.store.subscribe('currentRoute', (route) => {
            console.log('[App] Route changed to:', route);
            this.updateActiveNavItem(route);
        });

        // React to sidebar state
        this.store.subscribe('sidebarCollapsed', (collapsed) => {
            document.body.classList.toggle('sb-sidenav-toggled', collapsed);
        });

        // React to backend status
        this.store.subscribe('backendOnline', (online) => {
            this.updateBackendStatus(online);
        });

        console.log('[App] State subscriptions setup');
    }

    /**
     * Render appropriate view based on state
     */
    renderView(view) {
        const loginScreen = document.getElementById('login-screen');
        const appWrapper = document.getElementById('app-wrapper');
        
        if (!loginScreen || !appWrapper) {
            console.error('[App] Missing DOM elements');
            return;
        }
        
        if (view === 'login') {
            loginScreen.classList.remove('d-none');
            appWrapper.classList.add('d-none');
            console.log('[App] ✅ Login screen shown');
        } else if (view === 'app') {
            loginScreen.classList.add('d-none');
            appWrapper.classList.remove('d-none');
            console.log('[App] ✅ Application shown');
            
            // Load app metadata
            this.loadAppMetadata();
            
            // Start health check
            this.startHealthCheck();
            
            // Navigate to current route
            this.handleRoute();
        }
    }

    /**
     * Initialize application
     */
    async init() {
        console.log('[App] Starting initialization...');
        
        // Remove no-transition class after a brief delay
        setTimeout(() => {
            document.body.classList.remove('no-transition');
        }, 100);
        
        // Initialize theme FIRST
        this.theme.init();
        
        // Create and mount theme toggle
        this.createThemeToggle();
        
        // Show login screen initially
        this.renderView('login');
        
        // Setup routes
        this.setupRoutes();
        
        // Setup global event listeners
        this.setupEventListeners();
        
        // Check authentication
        if (this.auth.isAuthenticated()) {
            console.log('[App] Found existing token, verifying...');
            const verification = await this.auth.verify();
            
            if (verification.valid) {
                console.log('[App] Token valid, user:', verification.user);
                this.updateUserUI(verification.user);
                Toast.success(`Welcome back, ${verification.user}!`, { duration: 2000 });
            } else {
                console.log('[App] Token invalid');
                this.renderView('login');
            }
        } else {
            console.log('[App] No existing token');
        }
        
        console.log('[App] ✅ Initialization complete');
    }

    /**
     * Create theme toggle button
     */
    createThemeToggle() {
        const container = document.getElementById('theme-toggle-container');
        if (container) {
            const toggle = createThemeToggle(this.theme);
            container.appendChild(toggle);
            console.log('[App] Theme toggle created');
        }
    }

    /**
     * Register routes
     */
    setupRoutes() {
        const container = document.getElementById('main-content');
        
        // Temporary wrapper for old modules
        const createModuleWrapper = (moduleName) => {
            return class {
                constructor(container) {
                    this.container = container;
                    this.moduleName = moduleName;
                }
                
                async init() {
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
                const collapsed = this.store.get('sidebarCollapsed');
                this.store.set('sidebarCollapsed', !collapsed);
            });
        }

        // Logout button
        const logoutBtn = document.getElementById('logout-btn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.logout();
            });
        }

        // Login form
        const loginForm = document.getElementById('login-form');
        if (loginForm) {
            loginForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.handleLogin();
            });
        }

        console.log('[App] Event listeners setup');
    }

    /**
     * Handle route changes
     */
    async handleRoute() {
        const route = this.router.getCurrentRoute();
        this.store.set('currentRoute', route);
        
        await this.router.navigate(route);
        this.updatePageTitle(route);
    }

    /**
     * Update page title
     */
    updatePageTitle(route) {
        const titles = {
            'dashboard': 'Dashboard - Trishul SNMP',
            'simulator': 'Simulator - Trishul SNMP',
            'walker': 'Walker - Trishul SNMP',
            'traps': 'Traps - Trishul SNMP',
            'browser': 'Browser - Trishul SNMP',
            'mibs': 'MIBs - Trishul SNMP',
            'settings': 'Settings - Trishul SNMP'
        };
        
        document.title = titles[route] || 'Trishul SNMP';
    }

    /**
     * Update active navigation item
     */
    updateActiveNavItem(route) {
        document.querySelectorAll('.list-group-item').forEach(el => {
            const dataRoute = el.getAttribute('data-route');
            el.classList.toggle('active', dataRoute === route);
        });
    }

    /**
     * Handle login
     */
    async handleLogin() {
        const username = document.getElementById('username')?.value;
        const password = document.getElementById('password')?.value;
        const errorDiv = document.getElementById('login-error');
        
        if (!username || !password) {
            if (errorDiv) {
                errorDiv.textContent = 'Please enter username and password';
                errorDiv.classList.remove('d-none');
            }
            return;
        }
        
        // Hide error
        if (errorDiv) errorDiv.classList.add('d-none');
        
        try {
            const result = await this.auth.login(username, password);
            
            if (result.success) {
                console.log('[App] Login successful');
                this.updateUserUI(result.user);
                Toast.success(`Welcome, ${result.user}!`, { duration: 2000 });
            } else {
                console.error('[App] Login failed:', result.error);
                if (errorDiv) {
                    errorDiv.textContent = result.error;
                    errorDiv.classList.remove('d-none');
                }
            }
        } catch (error) {
            console.error('[App] Login error:', error);
            if (errorDiv) {
                errorDiv.textContent = 'An unexpected error occurred';
                errorDiv.classList.remove('d-none');
            }
        }
    }

    /**
     * Update user UI
     */
    updateUserUI(username) {
        const userDisplay = document.getElementById('username-display');
        if (userDisplay) {
            userDisplay.textContent = username || 'User';
        }
    }

    /**
     * Load app metadata
     */
    async loadAppMetadata() {
        try {
            const data = await this.api.get('/meta');
            
            this.store.update({
                appMetadata: data,
                backendOnline: true
            });
            
            console.log(`[App] 🔱 ${data.name} v${data.version} loaded`);
            
        } catch (error) {
            console.error('[App] Failed to load metadata:', error);
            this.store.set('backendOnline', false);
            Toast.warning('Backend is offline', { duration: 3000 });
        }
    }

    /**
     * Start health check
     */
    startHealthCheck() {
        if (this.healthCheckInterval) {
            clearInterval(this.healthCheckInterval);
        }
        
        this.healthCheckInterval = setInterval(async () => {
            await this.checkBackendHealth();
        }, 60000);
    }

    /**
     * Check backend health
     */
    async checkBackendHealth() {
        try {
            await this.api.get('/meta');
            
            const wasOffline = !this.store.get('backendOnline');
            if (wasOffline) {
                console.log('[App] Backend is back online');
                Toast.success('Backend connection restored', { duration: 2000 });
            }
            
            this.store.set('backendOnline', true);
            
        } catch (error) {
            const wasOnline = this.store.get('backendOnline');
            if (wasOnline) {
                console.error('[App] Backend went offline');
                Toast.error('Lost connection to backend', { duration: 3000 });
            }
            
            this.store.set('backendOnline', false);
        }
    }

    /**
     * Update backend status badge
     */
    updateBackendStatus(online) {
        const badge = document.getElementById('backend-status');
        if (badge) {
            badge.className = online ? 'badge bg-success' : 'badge bg-danger';
            const icon = badge.querySelector('i');
            const text = badge.querySelector('span');
            if (icon) icon.className = `fas fa-circle`;
            if (text) text.textContent = online ? 'Online' : 'Offline';
        }
    }

    /**
     * Logout
     */
    async logout() {
        if (this.isLoggingOut) {
            console.log('[App] Logout already in progress');
            return;
        }
        
        this.isLoggingOut = true;
        console.log('[App] Logging out...');
        
        if (this.healthCheckInterval) {
            clearInterval(this.healthCheckInterval);
        }
        
        await this.auth.logout();
        Toast.info('Logged out successfully', { duration: 2000 });
        
        setTimeout(() => {
            this.isLoggingOut = false;
        }, 1000);
    }
}

// Initialize app when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        console.log('[App] DOM loaded, initializing...');
        const app = new App();
        app.init().catch(error => {
            console.error('[App] Initialization failed:', error);
        });
    });
} else {
    console.log('[App] DOM already loaded, initializing immediately...');
    const app = new App();
    app.init().catch(error => {
        console.error('[App] Initialization failed:', error);
    });
}
