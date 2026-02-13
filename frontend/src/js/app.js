/**
 * Trishul SNMP - Main Application Entry Point
 * Modern ES6 Module-based Architecture with Reactive State Management
 */

import { Router } from './core/router.js';
import { AuthManager } from './core/auth.js';
import { ApiClient } from './core/api.js';
import { createAppStore } from './core/store.js';

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
        const wrapper = document.getElementById('wrapper');
        
        if (view === 'login') {
            if (loginScreen) loginScreen.style.display = 'flex';
            if (wrapper) wrapper.style.display = 'none';
            console.log('[App] Showing login screen');
        } else if (view === 'app') {
            if (loginScreen) loginScreen.style.display = 'none';
            if (wrapper) wrapper.style.display = 'flex';
            console.log('[App] Showing application');
            
            // Load app metadata when showing app
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
                // State store will trigger view change to 'app'
            } else {
                console.log('[App] Token invalid, clearing and showing login');
                // Clear invalid token
                sessionStorage.removeItem('snmp_token');
                sessionStorage.removeItem('snmp_user');
                this.store.set('currentView', 'login');
                // Explicitly render since state might not change
                this.renderView('login');
            }
        } else {
            console.log('[App] No existing token, showing login');
            this.store.set('currentView', 'login');
            // Explicitly render initial view
            this.renderView('login');
        }
    }

    /**
     * Register routes with their module classes
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
        }, { once: false }); // Allow multiple but we'll handle duplicates

        // Sidebar toggle
        const sidebarToggle = document.getElementById('sidebarToggle');
        if (sidebarToggle) {
            sidebarToggle.addEventListener('click', (e) => {
                e.preventDefault();
                const collapsed = this.store.get('sidebarCollapsed');
                this.store.set('sidebarCollapsed', !collapsed);
            });
        }

        // Login form - attach ONCE
        const loginForm = document.getElementById('login-form');
        if (loginForm && !loginForm.dataset.listenerAttached) {
            loginForm.addEventListener('submit', (e) => this.handleLogin(e));
            loginForm.dataset.listenerAttached = 'true';
            console.log('[App] Login form listener attached');
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
            'dashboard': 'Trishul SNMP',
            'simulator': 'SNMP Simulator',
            'walker': 'Walk & Parse',
            'traps': 'Trap Manager',
            'browser': 'MIB Browser',
            'mibs': 'MIB Manager',
            'settings': 'Settings'
        };

        const titleEl = document.getElementById('page-title');
        if (titleEl) {
            titleEl.textContent = titles[route] || 'Trishul SNMP';
        }
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
        
        const submitBtn = document.getElementById('login-btn');
        const errorDiv = document.getElementById('login-error');
        
        // Prevent double submission
        if (submitBtn.disabled) {
            console.log('[App] Login already in progress, ignoring');
            return;
        }
        
        const username = document.getElementById('login-user').value;
        const password = document.getElementById('login-pass').value;
        
        // Disable form
        submitBtn.disabled = true;
        errorDiv.classList.add('d-none');
        
        try {
            const result = await this.auth.login(username, password);
            
            if (result.success) {
                console.log('[App] Login successful');
                this.updateUserUI(result.user);
                // AuthManager will update store, triggering view change
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
        
        try {
            const data = await this.api.get('/meta');
            
            if (versionEl) {
                versionEl.textContent = `v${data.version}`;
                versionEl.title = `${data.name} v${data.version}`;
            }
            
            document.title = data.name;
            
            // Update store
            this.store.update({
                appMetadata: data,
                backendOnline: true
            });
            
            console.log(`[App] 🔱 ${data.name} v${data.version} loaded`);
            
        } catch (error) {
            console.error('[App] Failed to load metadata:', error);
            
            if (versionEl) {
                versionEl.textContent = 'Offline';
                versionEl.style.color = '#ef4444';
            }
            
            this.store.set('backendOnline', false);
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
        try {
            await this.api.get('/meta');
            
            const wasOffline = !this.store.get('backendOnline');
            if (wasOffline) {
                console.log('[App] Backend is back online');
            }
            
            this.store.set('backendOnline', true);
            
        } catch (error) {
            const wasOnline = this.store.get('backendOnline');
            if (wasOnline) {
                console.error('[App] Backend went offline');
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
            badge.textContent = online ? 'Online' : 'Offline';
        }
    }

    /**
     * Logout user
     */
    async logout() {
        // Prevent logout loop
        if (this.isLoggingOut) {
            console.log('[App] Logout already in progress, skipping');
            return;
        }
        
        this.isLoggingOut = true;
        console.log('[App] Logging out...');
        
        // Stop health check
        if (this.healthCheckInterval) {
            clearInterval(this.healthCheckInterval);
        }
        
        await this.auth.logout();
        // AuthManager will update store, triggering view change to 'login'
        
        // Reset flag after a delay
        setTimeout(() => {
            this.isLoggingOut = false;
        }, 1000);
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
