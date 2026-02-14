/**
 * Router - Handles client-side routing and module loading
 */
export class Router {
    constructor() {
        this.routes = new Map();
        this.currentModule = null;
        this.containerId = null;
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
        if (container && container.id) {
            this.containerId = container.id;
            console.log('[Router] Container ID set:', this.containerId);
        } else {
            console.error('[Router] Invalid container provided');
        }
        return this;
    }

    /**
     * Get the current container element (re-query from DOM)
     */
    getContainer() {
        if (!this.containerId) {
            console.error('[Router] No container ID set!');
            return null;
        }
        
        const container = document.getElementById(this.containerId);
        if (!container) {
            console.error(`[Router] Container #${this.containerId} not found in DOM!`);
        }
        return container;
    }

    /**
     * Navigate to a route
     */
    async navigate(path) {
        console.log(`[Router] Navigating to: ${path}`);

        // Re-query container from DOM
        const container = this.getContainer();
        if (!container) {
            console.error('[Router] Cannot navigate - no container!');
            return;
        }

        // Show loading spinner
        this.showLoading(container, path);

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
            this.showError(container, `Route not found: ${path}`);
            return;
        }

        try {
            console.log('[Router] Creating module instance...');
            
            // Pass container getter instead of container itself
            this.currentModule = new ModuleClass(container, () => this.getContainer());
            
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
            
            // Re-query container for error display
            const errorContainer = this.getContainer();
            if (errorContainer) {
                this.showError(errorContainer, `Failed to load ${path}: ${error.message}`, error.stack);
            }
        }
    }

    /**
     * Show loading spinner
     */
    showLoading(container, route) {
        if (!container) return;
        
        container.innerHTML = `
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
    showError(container, message, stack = '') {
        if (!container) return;
        
        const stackTrace = stack ? `
            <hr>
            <details>
                <summary class="text-muted" style="cursor: pointer;">Show error details</summary>
                <pre class="mt-2 p-3 bg-light rounded" style="font-size: 0.85rem; max-height: 300px; overflow: auto;">${stack}</pre>
            </details>
        ` : '';
        
        container.innerHTML = `
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
