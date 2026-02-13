/**
 * Base Component Class
 * Provides lifecycle management, store integration, and reactive updates
 */

export class Component {
    constructor(container, props = {}, store = null) {
        this.container = container;
        this.props = props;
        this.store = store;
        this.state = {};
        this.element = null;
        this.subscriptions = [];
        this.isMounted = false;
        
        console.log(`[Component] ${this.constructor.name} created`);
    }

    /**
     * Initialize component
     */
    async init() {
        console.log(`[Component] ${this.constructor.name} initializing...`);
        
        // Call lifecycle: beforeMount
        await this.beforeMount();
        
        // Render component
        const html = await this.render();
        
        if (typeof this.container === 'string') {
            this.container = document.querySelector(this.container);
        }
        
        if (!this.container) {
            console.error(`[Component] ${this.constructor.name}: Container not found`);
            return;
        }
        
        // Insert into DOM
        if (typeof html === 'string') {
            this.container.innerHTML = html;
            this.element = this.container.firstElementChild || this.container;
        } else if (html instanceof HTMLElement) {
            this.container.innerHTML = '';
            this.container.appendChild(html);
            this.element = html;
        }
        
        this.isMounted = true;
        
        // Call lifecycle: mounted
        await this.mounted();
        
        console.log(`[Component] ${this.constructor.name} mounted`);
    }

    /**
     * Lifecycle: Before component mounts
     */
    async beforeMount() {
        // Override in child components
    }

    /**
     * Lifecycle: Component mounted to DOM
     */
    async mounted() {
        // Override in child components
    }

    /**
     * Lifecycle: Before component updates
     */
    async beforeUpdate() {
        // Override in child components
    }

    /**
     * Lifecycle: Component updated
     */
    async updated() {
        // Override in child components
    }

    /**
     * Lifecycle: Before component unmounts
     */
    async beforeUnmount() {
        // Override in child components
    }

    /**
     * Lifecycle: Component unmounted
     */
    async unmounted() {
        // Override in child components
    }

    /**
     * Render component HTML
     * Must be implemented by child components
     */
    render() {
        throw new Error(`${this.constructor.name} must implement render() method`);
    }

    /**
     * Update component with new props
     */
    async update(newProps = {}) {
        if (!this.isMounted) {
            console.warn(`[Component] ${this.constructor.name}: Cannot update before mount`);
            return;
        }
        
        await this.beforeUpdate();
        
        this.props = { ...this.props, ...newProps };
        
        // Re-render
        const html = await this.render();
        
        if (typeof html === 'string') {
            this.container.innerHTML = html;
            this.element = this.container.firstElementChild || this.container;
        } else if (html instanceof HTMLElement) {
            this.container.innerHTML = '';
            this.container.appendChild(html);
            this.element = html;
        }
        
        await this.updated();
        
        console.log(`[Component] ${this.constructor.name} updated`);
    }

    /**
     * Set component state (reactive)
     */
    setState(updates) {
        const oldState = { ...this.state };
        this.state = { ...this.state, ...updates };
        
        // Trigger update if mounted
        if (this.isMounted) {
            this.update();
        }
    }

    /**
     * Subscribe to store changes
     */
    subscribe(keys, callback) {
        if (!this.store) {
            console.warn(`[Component] ${this.constructor.name}: No store available`);
            return;
        }
        
        const unsubscribe = this.store.subscribe(keys, callback);
        this.subscriptions.push(unsubscribe);
        
        return unsubscribe;
    }

    /**
     * Query selector within component
     */
    $(selector) {
        return this.element ? this.element.querySelector(selector) : null;
    }

    /**
     * Query selector all within component
     */
    $$(selector) {
        return this.element ? this.element.querySelectorAll(selector) : [];
    }

    /**
     * Add event listener to component element
     */
    on(event, selector, handler) {
        if (!this.element) return;
        
        if (typeof selector === 'function') {
            // Direct binding
            handler = selector;
            this.element.addEventListener(event, handler);
        } else {
            // Delegated binding
            this.element.addEventListener(event, (e) => {
                const target = e.target.closest(selector);
                if (target) {
                    handler.call(target, e);
                }
            });
        }
    }

    /**
     * Emit custom event
     */
    emit(eventName, detail = {}) {
        const event = new CustomEvent(eventName, {
            detail,
            bubbles: true,
            cancelable: true
        });
        
        if (this.element) {
            this.element.dispatchEvent(event);
        }
        
        console.log(`[Component] ${this.constructor.name} emitted '${eventName}'`, detail);
    }

    /**
     * Destroy component
     */
    async destroy() {
        console.log(`[Component] ${this.constructor.name} destroying...`);
        
        await this.beforeUnmount();
        
        // Unsubscribe from all store subscriptions
        this.subscriptions.forEach(unsubscribe => unsubscribe());
        this.subscriptions = [];
        
        // Remove from DOM
        if (this.element && this.element.parentNode) {
            this.element.remove();
        }
        
        this.isMounted = false;
        
        await this.unmounted();
        
        console.log(`[Component] ${this.constructor.name} destroyed`);
    }

    /**
     * Show component
     */
    show() {
        if (this.element) {
            this.element.style.display = '';
        }
    }

    /**
     * Hide component
     */
    hide() {
        if (this.element) {
            this.element.style.display = 'none';
        }
    }

    /**
     * Toggle component visibility
     */
    toggle() {
        if (this.element) {
            const isHidden = this.element.style.display === 'none';
            this.element.style.display = isHidden ? '' : 'none';
        }
    }
}

/**
 * Create element helper
 */
export function createElement(tag, attrs = {}, ...children) {
    const element = document.createElement(tag);
    
    // Set attributes
    Object.entries(attrs).forEach(([key, value]) => {
        if (key === 'className') {
            element.className = value;
        } else if (key === 'style' && typeof value === 'object') {
            Object.assign(element.style, value);
        } else if (key.startsWith('on') && typeof value === 'function') {
            const event = key.substring(2).toLowerCase();
            element.addEventListener(event, value);
        } else {
            element.setAttribute(key, value);
        }
    });
    
    // Append children
    children.flat().forEach(child => {
        if (child == null) return;
        
        if (typeof child === 'string' || typeof child === 'number') {
            element.appendChild(document.createTextNode(child));
        } else if (child instanceof HTMLElement) {
            element.appendChild(child);
        }
    });
    
    return element;
}

/**
 * HTML template tag function for syntax highlighting
 */
export function html(strings, ...values) {
    return strings.reduce((result, str, i) => {
        const value = values[i] != null ? values[i] : '';
        return result + str + value;
    }, '');
}
