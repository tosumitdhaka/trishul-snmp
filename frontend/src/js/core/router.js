/**
 * Router - Handles client-side routing and module loading
 */
export class Router {
    constructor() {
        this.routes = new Map();
        this.currentModule = null;
        this.container = null;
    }

    /**
     * Register a route with its module class
     */
    register(path, moduleClass) {
        this.routes.set(path, moduleClass);
        return this;
    }

    /**
     * Set the container element for modules
     */
    setContainer(container) {
        this.container = container;
        return this;
    }

    /**
     * Navigate to a route
     */
    async navigate(path) {
        console.log(`[Router] Navigating to: ${path}`);

        // Destroy current module if exists
        if (this.currentModule?.destroy) {
            try {
                await this.currentModule.destroy();
            } catch (error) {
                console.error('[Router] Error destroying module:', error);
            }
        }

        // Get module class for route
        const ModuleClass = this.routes.get(path);
        
        if (!ModuleClass) {
            console.error(`[Router] No module found for route: ${path}`);
            this.showError(`Route not found: ${path}`);
            return;
        }

        try {
            // Create and initialize new module
            this.currentModule = new ModuleClass(this.container);
            
            if (typeof this.currentModule.init === 'function') {
                await this.currentModule.init();
            } else {
                console.warn('[Router] Module does not have init() method');
            }

            // Update page title
            this.updatePageTitle(path);
            
        } catch (error) {
            console.error('[Router] Error loading module:', error);
            this.showError(`Failed to load ${path}: ${error.message}`);
        }
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
    }

    /**
     * Show error message in container
     */
    showError(message) {
        if (!this.container) return;
        
        this.container.innerHTML = `
            <div class="alert alert-danger" role="alert">
                <i class="fas fa-exclamation-triangle me-2"></i>
                <strong>Error:</strong> ${message}
            </div>
        `;
    }

    /**
     * Get current route from hash
     */
    getCurrentRoute() {
        return window.location.hash.substring(1) || 'dashboard';
    }
}
