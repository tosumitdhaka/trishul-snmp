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
    
    if (response.status === 401 && !url.includes('/login') && !url.includes('/logout')) {
        console.warn('[Fetch Interceptor] 401 Unauthorized - triggering logout');
        if (window.app && window.app.store.get('isAuthenticated')) {
            window.dispatchEvent(new CustomEvent('auth:unauthorized'));
        }
    }

    return response;
};

console.log('[App] Fetch interceptor installed');

class App {
    constructor() {
        this.store = createAppStore();
        this.router = new Router();
        this.auth = new AuthManager(this.store);
        this.api = new ApiClient();
        this.theme = new ThemeManager(this.store);
        this.isLoggingOut = false;
        
        this.setupStateSubscriptions();
        window.app = this;
        
        console.log('[App] Trishul SNMP initializing...');
    }

    setupStateSubscriptions() {
        this.store.subscribe('currentView', (view) => {
            console.log('[App] View changed to:', view);
            this.renderView(view);
        });

        this.store.subscribe('currentRoute', (route) => {
            console.log('[App] Route changed to:', route);
            this.updateActiveNavItem(route);
        });

        this.store.subscribe('sidebarCollapsed', (collapsed) => {
            document.body.classList.toggle('sb-sidenav-toggled', collapsed);
        });

        this.store.subscribe('backendOnline', (online) => {
            this.updateBackendStatus(online);
        });

        console.log('[App] State subscriptions setup');
    }

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
            
            // Setup routes NOW that app-wrapper is visible
            if (!this.routesSetup) {
                this.setupRoutes();
                this.routesSetup = true;
            }
            
            this.loadAppMetadata();
            this.startHealthCheck();
            this.handleRoute();
        }
    }

    async init() {
        console.log('[App] Starting initialization...');
        
        setTimeout(() => {
            document.body.classList.remove('no-transition');
        }, 100);
        
        this.theme.init();
        this.createThemeToggle();
        this.renderView('login');
        this.setupEventListeners();
        
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

    createThemeToggle() {
        const container = document.getElementById('theme-toggle-container');
        if (container) {
            const toggle = createThemeToggle(this.theme);
            container.appendChild(toggle);
            console.log('[App] Theme toggle created');
        }
    }

    setupRoutes() {
        console.log('[App] Setting up routes...');
        
        const container = document.getElementById('main-content');
        console.log('[App] Container element:', container);
        
        if (!container) {
            console.error('[App] ❌ main-content container not found!');
            return;
        }
        
        // Create wrapper that re-queries container
        const createModuleWrapper = (moduleName) => {
            return class {
                constructor(initialContainer, containerGetter) {
                    this.moduleName = moduleName;
                    this.containerGetter = containerGetter || (() => document.getElementById('main-content'));
                    console.log(`[Module:${moduleName}] Created`);
                }
                
                async init() {
                    console.log(`[Module:${this.moduleName}] Fetching ${this.moduleName}.html...`);
                    
                    const response = await fetch(`${this.moduleName}.html`);
                    
                    if (!response.ok) {
                        console.error(`[Module:${this.moduleName}] Failed to fetch: ${response.status}`);
                        throw new Error(`Module not found: ${response.statusText}`);
                    }
                    
                    const html = await response.text();
                    console.log(`[Module:${this.moduleName}] Loaded ${html.length} bytes`);
                    
                    // Re-query container before injecting
                    const container = this.containerGetter();
                    if (!container) {
                        console.error(`[Module:${this.moduleName}] Container disappeared!`);
                        throw new Error('Container element not found');
                    }
                    
                    container.innerHTML = html;
                    console.log(`[Module:${this.moduleName}] ✅ HTML injected into container`);
                    
                    // Wait a tick for DOM to settle
                    await new Promise(resolve => setTimeout(resolve, 50));
                    
                    // Verify content is still there
                    const verifyContainer = this.containerGetter();
                    if (verifyContainer && verifyContainer.children.length > 0) {
                        console.log(`[Module:${this.moduleName}] ✅ Content verified: ${verifyContainer.children.length} elements`);
                    } else {
                        console.warn(`[Module:${this.moduleName}] ⚠️ Content may have been removed!`);
                    }
                    
                    // Initialize old module if exists
                    const capitalizedName = this.moduleName.charAt(0).toUpperCase() + this.moduleName.slice(1);
                    const oldModule = window[`${capitalizedName}Module`];
                    
                    if (oldModule && typeof oldModule.init === 'function') {
                        console.log(`[Module:${this.moduleName}] Initializing ${capitalizedName}Module...`);
                        oldModule.init();
                    } else {
                        console.log(`[Module:${this.moduleName}] No ${capitalizedName}Module found, HTML only`);
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
        
        console.log('[App] ✅ Routes registered');
    }

    setupEventListeners() {
        window.addEventListener('hashchange', () => {
            this.handleRoute();
        });

        window.addEventListener('auth:unauthorized', () => {
            console.log('[App] Unauthorized event received');
            this.logout();
        });

        const sidebarToggle = document.getElementById('sidebarToggle');
        if (sidebarToggle) {
            sidebarToggle.addEventListener('click', (e) => {
                e.preventDefault();
                const collapsed = this.store.get('sidebarCollapsed');
                this.store.set('sidebarCollapsed', !collapsed);
            });
        }

        const logoutBtn = document.getElementById('logout-btn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.logout();
            });
        }

        const loginForm = document.getElementById('login-form');
        if (loginForm) {
            loginForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.handleLogin();
            });
        }

        console.log('[App] Event listeners setup');
    }

    async handleRoute() {
        const route = this.router.getCurrentRoute();
        this.store.set('currentRoute', route);
        
        await this.router.navigate(route);
        this.updatePageTitle(route);
    }

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

    updateActiveNavItem(route) {
        document.querySelectorAll('.list-group-item').forEach(el => {
            const dataRoute = el.getAttribute('data-route');
            el.classList.toggle('active', dataRoute === route);
        });
    }

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

    updateUserUI(username) {
        const userDisplay = document.getElementById('username-display');
        if (userDisplay) {
            userDisplay.textContent = username || 'User';
        }
    }

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

    startHealthCheck() {
        if (this.healthCheckInterval) {
            clearInterval(this.healthCheckInterval);
        }
        
        this.healthCheckInterval = setInterval(async () => {
            await this.checkBackendHealth();
        }, 60000);
    }

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
