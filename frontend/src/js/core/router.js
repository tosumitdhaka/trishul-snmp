/**
 * Router - Handles client-side routing and module loading
 */
export class Router {
    constructor() {
        this.routes = new Map();
        this.currentModule = null;
        this.container = null;
        console.log('[Router] Initialized');
    }

    /**
     * Register a route with its module class
     */
    register(path, moduleClass) {
        this.routes.set(path, moduleClass);
        console.log(`[Router] Route registered: ${path}`);
        return this;
    }

    /**
     * Set the container element for modules
     */
    setContainer(container) {
        this.container = container;
        console.log('[Router] Container set:', container?.id || 'unknown');
        return this;
    }

    /**
     * Navigate to a route
     */
    async navigate(path) {
        console.log(`[Router] Navigating to: ${path}`);

        if (!this.container) {
            console.error('[Router] No container set!');
            return;
        }

        // Show loading spinner
        this.showLoading(path);

        // Destroy current module if exists
        if (this.currentModule?.destroy) {
            try {
                console.log('[Router] Destroying previous module');
                await this.currentModule.destroy();
            } catch (error) {
                console.error('[Router] Error destroying module:', error);
            }
        }

        // Get module class for route
        const ModuleClass = this.routes.get(path);
        
        if (!ModuleClass) {
            console.error(`[Router] No module found for route: ${path}`);
            console.log('[Router] Available routes:', Array.from(this.routes.keys()));
            this.showError(`Route not found: ${path}`);
            return;
        }

        try {
            console.log('[Router] Creating module instance...');
            // Create and initialize new module
            this.currentModule = new ModuleClass(this.container);
            
            if (typeof this.currentModule.init === 'function') {
                console.log('[Router] Initializing module...');
                await this.currentModule.init();
                console.log('[Router] ✅ Module loaded successfully:', path);
            } else {
                console.warn('[Router] Module does not have init() method');
                console.warn('[Router] Module:', this.currentModule);
            }

            // Update page title
            this.updatePageTitle(path);
            
        } catch (error) {
            console.error('[Router] ❌ Error loading module:', error);
            console.error('[Router] Error stack:', error.stack);
            this.showError(`Failed to load ${path}: ${error.message}`, error.stack);
        }
    }

    /**
     * Show loading spinner
     */
    showLoading(route) {
        if (!this.container) return;
        
        this.container.innerHTML = `
            <div class="text-center py-5">
                <div class="spinner-border text-primary" role="status" style="width: 3rem; height: 3rem;">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p class="mt-3 text-muted">Loading ${route}...</p>
            </div>
        `;
    }

    /**
     * Update page title based on route
     */
    updatePageTitle(route) {
        const titles = {
            'dashboard': 'Dashboard',
            'simulator': 'SNMP Simulator',
            'walker': 'Walk & Parse',
            'traps': 'Trap Manager',
            'browser': 'MIB Browser',
            'mibs': 'MIB Manager',
            'settings': 'Settings'
        };

        const title = titles[route] || 'Trishul SNMP';
        const pageTitle = document.getElementById('page-title');
        
        if (pageTitle) {
            pageTitle.textContent = title;
        }
        
        document.title = `${title} - Trishul SNMP`;
    }

    /**
     * Show error message in container
     */
    showError(message, stack = '') {
        if (!this.container) return;
        
        const stackTrace = stack ? `
            <hr>
            <details>
                <summary class="text-muted" style="cursor: pointer;">Show error details</summary>
                <pre class="mt-2 p-3 bg-light rounded" style="font-size: 0.85rem; max-height: 300px; overflow: auto;">${stack}</pre>
            </details>
        ` : '';
        
        this.container.innerHTML = `
            <div class="alert alert-danger" role="alert">
                <h4 class="alert-heading">
                    <i class="fas fa-exclamation-triangle me-2"></i>
                    Error Loading Module
                </h4>
                <p><strong>${message}</strong></p>
                ${stackTrace}
                <hr>
                <p class="mb-0">
                    <a href="#dashboard" class="alert-link">← Go to Dashboard</a>
                </p>
            </div>
        `;
    }

    /**
     * Get current route from hash
     */
    getCurrentRoute() {
        const route = window.location.hash.substring(1) || 'dashboard';
        console.log('[Router] Current route:', route);
        return route;
    }
}
