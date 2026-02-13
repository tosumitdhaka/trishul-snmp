/**
 * Accessibility Utilities
 */

/**
 * Focus management
 */
export class FocusManager {
    constructor() {
        this.focusableSelectors = [
            'a[href]',
            'area[href]',
            'input:not([disabled])',
            'select:not([disabled])',
            'textarea:not([disabled])',
            'button:not([disabled])',
            '[tabindex]:not([tabindex="-1"])'
        ].join(',');
    }

    /**
     * Get all focusable elements in a container
     */
    getFocusableElements(container = document) {
        return Array.from(container.querySelectorAll(this.focusableSelectors))
            .filter(el => this.isVisible(el));
    }

    /**
     * Check if element is visible
     */
    isVisible(element) {
        if (!element) return false;
        return element.offsetWidth > 0 && 
               element.offsetHeight > 0 && 
               getComputedStyle(element).visibility !== 'hidden';
    }

    /**
     * Trap focus within container (for modals, etc.)
     */
    trapFocus(container, onEscape) {
        const focusable = this.getFocusableElements(container);
        const firstFocusable = focusable[0];
        const lastFocusable = focusable[focusable.length - 1];
        
        // Focus first element
        if (firstFocusable) {
            firstFocusable.focus();
        }
        
        const handleKeydown = (e) => {
            // Escape key
            if (e.key === 'Escape' && onEscape) {
                onEscape();
                return;
            }
            
            // Tab navigation
            if (e.key !== 'Tab') return;
            
            // Shift + Tab
            if (e.shiftKey) {
                if (document.activeElement === firstFocusable) {
                    e.preventDefault();
                    lastFocusable.focus();
                }
            }
            // Tab
            else {
                if (document.activeElement === lastFocusable) {
                    e.preventDefault();
                    firstFocusable.focus();
                }
            }
        };
        
        document.addEventListener('keydown', handleKeydown);
        
        // Return cleanup function
        return () => {
            document.removeEventListener('keydown', handleKeydown);
        };
    }

    /**
     * Save and restore focus
     */
    saveFocus() {
        const activeElement = document.activeElement;
        return () => {
            if (activeElement && activeElement.focus) {
                activeElement.focus();
            }
        };
    }
}

/**
 * ARIA live region announcer
 */
export class Announcer {
    constructor() {
        this.region = this.createRegion();
    }

    createRegion() {
        let region = document.getElementById('aria-announcer');
        if (!region) {
            region = document.createElement('div');
            region.id = 'aria-announcer';
            region.setAttribute('role', 'status');
            region.setAttribute('aria-live', 'polite');
            region.setAttribute('aria-atomic', 'true');
            region.className = 'sr-only';
            document.body.appendChild(region);
        }
        return region;
    }

    /**
     * Announce message to screen readers
     */
    announce(message, priority = 'polite') {
        this.region.setAttribute('aria-live', priority); // 'polite' or 'assertive'
        this.region.textContent = '';
        
        // Small delay for screen readers to pick up change
        setTimeout(() => {
            this.region.textContent = message;
        }, 100);
    }
}

/**
 * Keyboard navigation helper
 */
export class KeyboardNav {
    /**
     * Make list navigable with arrow keys
     */
    static makeListNavigable(container, itemSelector, options = {}) {
        const {
            onSelect = () => {},
            loop = true,
            orientation = 'vertical' // 'vertical' or 'horizontal'
        } = options;
        
        const nextKey = orientation === 'vertical' ? 'ArrowDown' : 'ArrowRight';
        const prevKey = orientation === 'vertical' ? 'ArrowUp' : 'ArrowLeft';
        
        container.addEventListener('keydown', (e) => {
            const items = Array.from(container.querySelectorAll(itemSelector));
            const currentIndex = items.indexOf(document.activeElement);
            
            if (currentIndex === -1) return;
            
            let nextIndex = currentIndex;
            
            switch (e.key) {
                case nextKey:
                    e.preventDefault();
                    nextIndex = currentIndex + 1;
                    if (nextIndex >= items.length) {
                        nextIndex = loop ? 0 : currentIndex;
                    }
                    break;
                    
                case prevKey:
                    e.preventDefault();
                    nextIndex = currentIndex - 1;
                    if (nextIndex < 0) {
                        nextIndex = loop ? items.length - 1 : currentIndex;
                    }
                    break;
                    
                case 'Home':
                    e.preventDefault();
                    nextIndex = 0;
                    break;
                    
                case 'End':
                    e.preventDefault();
                    nextIndex = items.length - 1;
                    break;
                    
                case 'Enter':
                case ' ':
                    e.preventDefault();
                    onSelect(items[currentIndex], currentIndex);
                    return;
            }
            
            if (nextIndex !== currentIndex && items[nextIndex]) {
                items[nextIndex].focus();
            }
        });
    }
}

/**
 * Screen reader only text
 */
export function createSROnly(text) {
    const span = document.createElement('span');
    span.className = 'sr-only';
    span.textContent = text;
    return span;
}

/**
 * Add skip link
 */
export function addSkipLink(targetId, text = 'Skip to main content') {
    const skipLink = document.createElement('a');
    skipLink.href = `#${targetId}`;
    skipLink.className = 'skip-link';
    skipLink.textContent = text;
    document.body.insertBefore(skipLink, document.body.firstChild);
    return skipLink;
}

/**
 * Global instances
 */
export const focusManager = new FocusManager();
export const announcer = new Announcer();
