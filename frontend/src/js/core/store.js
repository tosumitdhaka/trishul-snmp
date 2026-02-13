/**
 * Centralized State Store
 * Implements reactive state management with pub/sub pattern
 */

export class Store {
    constructor(initialState = {}) {
        this.state = this.createProxy(initialState);
        this.subscribers = new Map(); // key -> Set of callbacks
        this.middlewares = [];
        
        console.log('[Store] State store initialized');
    }

    /**
     * Create a reactive proxy that triggers subscribers on changes
     */
    createProxy(target) {
        const store = this;
        
        return new Proxy(target, {
            set(obj, prop, value) {
                const oldValue = obj[prop];
                
                // Only trigger if value actually changed
                if (oldValue !== value) {
                    obj[prop] = value;
                    
                    // Run middlewares
                    store.runMiddlewares(prop, value, oldValue);
                    
                    // Notify subscribers
                    store.notify(prop, value, oldValue);
                    
                    console.log(`[Store] State changed: ${prop}`, value);
                }
                
                return true;
            },
            
            get(obj, prop) {
                const value = obj[prop];
                
                // If value is an object, make it reactive too
                if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
                    return store.createProxy(value);
                }
                
                return value;
            }
        });
    }

    /**
     * Get current state value
     */
    get(key) {
        return this.state[key];
    }

    /**
     * Set state value
     */
    set(key, value) {
        this.state[key] = value;
    }

    /**
     * Update multiple state values at once
     */
    update(updates) {
        Object.keys(updates).forEach(key => {
            this.state[key] = updates[key];
        });
    }

    /**
     * Subscribe to state changes
     * @param {string|string[]} keys - State key(s) to watch
     * @param {Function} callback - Function to call on change
     * @returns {Function} Unsubscribe function
     */
    subscribe(keys, callback) {
        const keyArray = Array.isArray(keys) ? keys : [keys];
        
        keyArray.forEach(key => {
            if (!this.subscribers.has(key)) {
                this.subscribers.set(key, new Set());
            }
            this.subscribers.get(key).add(callback);
        });

        // Return unsubscribe function
        return () => {
            keyArray.forEach(key => {
                const callbacks = this.subscribers.get(key);
                if (callbacks) {
                    callbacks.delete(callback);
                }
            });
        };
    }

    /**
     * Notify subscribers of state change
     */
    notify(key, newValue, oldValue) {
        const callbacks = this.subscribers.get(key);
        if (callbacks) {
            callbacks.forEach(callback => {
                try {
                    callback(newValue, oldValue, key);
                } catch (error) {
                    console.error(`[Store] Error in subscriber for '${key}':`, error);
                }
            });
        }
    }

    /**
     * Add middleware for state changes
     */
    use(middleware) {
        this.middlewares.push(middleware);
    }

    /**
     * Run middlewares
     */
    runMiddlewares(key, newValue, oldValue) {
        this.middlewares.forEach(middleware => {
            try {
                middleware(key, newValue, oldValue, this.state);
            } catch (error) {
                console.error('[Store] Middleware error:', error);
            }
        });
    }

    /**
     * Clear all state
     */
    clear() {
        Object.keys(this.state).forEach(key => {
            delete this.state[key];
        });
        console.log('[Store] State cleared');
    }

    /**
     * Get entire state snapshot (non-reactive)
     */
    snapshot() {
        return JSON.parse(JSON.stringify(this.state));
    }
}

/**
 * Persistence Middleware
 * Automatically saves specified state keys to localStorage
 */
export class PersistenceMiddleware {
    constructor(keys = [], storageKey = 'app_state') {
        this.keys = new Set(keys);
        this.storageKey = storageKey;
        
        console.log('[PersistenceMiddleware] Initialized for keys:', keys);
    }

    middleware = (key, newValue, oldValue, state) => {
        if (this.keys.has(key)) {
            this.save(key, newValue);
        }
    }

    save(key, value) {
        try {
            const stored = this.load();
            stored[key] = value;
            localStorage.setItem(this.storageKey, JSON.stringify(stored));
            console.log(`[PersistenceMiddleware] Saved '${key}' to localStorage`);
        } catch (error) {
            console.error('[PersistenceMiddleware] Save failed:', error);
        }
    }

    load() {
        try {
            const data = localStorage.getItem(this.storageKey);
            return data ? JSON.parse(data) : {};
        } catch (error) {
            console.error('[PersistenceMiddleware] Load failed:', error);
            return {};
        }
    }

    restore(store) {
        const saved = this.load();
        Object.keys(saved).forEach(key => {
            if (this.keys.has(key)) {
                store.set(key, saved[key]);
                console.log(`[PersistenceMiddleware] Restored '${key}' from localStorage`);
            }
        });
    }
}

/**
 * Logger Middleware
 * Logs all state changes
 */
export class LoggerMiddleware {
    constructor(options = {}) {
        this.enabled = options.enabled !== false;
        this.collapsed = options.collapsed !== false;
    }

    middleware = (key, newValue, oldValue) => {
        if (!this.enabled) return;

        if (this.collapsed) {
            console.groupCollapsed(
                `%c[State Change] ${key}`,
                'color: #3b82f6; font-weight: bold;'
            );
        } else {
            console.group(`[State Change] ${key}`);
        }

        console.log('%cPrevious:', 'color: #ef4444;', oldValue);
        console.log('%cCurrent:', 'color: #10b981;', newValue);
        console.trace('Stack trace');
        console.groupEnd();
    }
}

/**
 * Create the global application store
 */
export function createAppStore() {
    const store = new Store({
        // Authentication
        isAuthenticated: false,
        user: null,
        token: null,
        
        // UI State
        currentView: 'login', // 'login' | 'app'
        currentRoute: 'dashboard',
        sidebarCollapsed: false,
        
        // App State
        backendOnline: false,
        appMetadata: null,
        
        // Module States (will be populated by modules)
        simulator: null,
        walker: null,
        traps: null,
        browser: null,
        mibs: null,
        settings: null
    });

    // Add persistence for specific keys
    const persistence = new PersistenceMiddleware(
        ['sidebarCollapsed', 'currentRoute'],
        'trishul_state'
    );
    store.use(persistence.middleware);
    persistence.restore(store);

    // Add logger in development
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
        const logger = new LoggerMiddleware({ collapsed: true });
        store.use(logger.middleware);
    }

    // Make store globally accessible for debugging
    window.__store__ = store;

    console.log('[Store] Application store created');
    return store;
}
