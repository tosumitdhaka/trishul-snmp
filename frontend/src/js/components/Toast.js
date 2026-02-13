/**
 * Toast Notification Component
 * Non-intrusive notification system with auto-dismiss
 */

import { Component, html } from '../core/component.js';

export class Toast extends Component {
    constructor(container, props = {}) {
        super(container, {
            message: '',
            type: 'info', // 'success', 'error', 'warning', 'info'
            icon: null,
            duration: 3000, // 0 = no auto-dismiss
            position: 'top-right', // 'top-right', 'top-left', 'bottom-right', 'bottom-left', 'top-center', 'bottom-center'
            dismissible: true,
            ...props
        });
        
        this.timeoutId = null;
    }

    render() {
        const { message, type, icon, dismissible } = this.props;
        
        const iconMap = {
            success: 'fas fa-check-circle',
            error: 'fas fa-exclamation-circle',
            warning: 'fas fa-exclamation-triangle',
            info: 'fas fa-info-circle'
        };
        
        const typeColors = {
            success: 'success',
            error: 'danger',
            warning: 'warning',
            info: 'info'
        };
        
        const toastIcon = icon || iconMap[type] || iconMap.info;
        const toastColor = typeColors[type] || typeColors.info;
        
        return html`
            <div class="toast align-items-center text-bg-${toastColor} border-0" 
                 role="alert" 
                 aria-live="assertive" 
                 aria-atomic="true"
                 data-toast>
                <div class="d-flex">
                    <div class="toast-body">
                        <i class="${toastIcon} me-2"></i>
                        ${message}
                    </div>
                    ${dismissible ? html`
                        <button type="button" 
                                class="btn-close btn-close-white me-2 m-auto" 
                                data-dismiss
                                aria-label="Close"></button>
                    ` : ''}
                </div>
            </div>
        `;
    }

    async mounted() {
        // Setup dismiss button
        if (this.props.dismissible) {
            this.on('click', '[data-dismiss]', () => {
                this.dismiss();
            });
        }
        
        // Show animation
        setTimeout(() => {
            if (this.element) {
                this.element.classList.add('show');
            }
        }, 10);
        
        // Auto-dismiss
        if (this.props.duration > 0) {
            this.timeoutId = setTimeout(() => {
                this.dismiss();
            }, this.props.duration);
        }
    }

    dismiss() {
        if (this.element) {
            this.element.classList.remove('show');
            
            // Wait for animation
            setTimeout(() => {
                this.destroy();
            }, 300);
        }
        
        // Clear timeout
        if (this.timeoutId) {
            clearTimeout(this.timeoutId);
        }
    }

    async beforeUnmount() {
        if (this.timeoutId) {
            clearTimeout(this.timeoutId);
        }
    }
}

/**
 * Toast Manager
 * Manages toast notifications with queue and positioning
 */
export class ToastManager {
    constructor() {
        this.containers = {};
        this.queue = [];
        this.maxVisible = 3;
        
        console.log('[Toast] ToastManager initialized');
    }

    /**
     * Get or create container for position
     */
    getContainer(position = 'top-right') {
        if (!this.containers[position]) {
            const container = document.createElement('div');
            container.className = `toast-container position-fixed p-3 ${this.getPositionClass(position)}`;
            container.style.zIndex = '9999';
            document.body.appendChild(container);
            
            this.containers[position] = container;
        }
        
        return this.containers[position];
    }

    /**
     * Get Bootstrap position class
     */
    getPositionClass(position) {
        const positions = {
            'top-right': 'top-0 end-0',
            'top-left': 'top-0 start-0',
            'top-center': 'top-0 start-50 translate-middle-x',
            'bottom-right': 'bottom-0 end-0',
            'bottom-left': 'bottom-0 start-0',
            'bottom-center': 'bottom-0 start-50 translate-middle-x'
        };
        
        return positions[position] || positions['top-right'];
    }

    /**
     * Show a toast
     */
    async show(message, type = 'info', options = {}) {
        const container = this.getContainer(options.position || 'top-right');
        
        // Create temporary div for toast
        const toastDiv = document.createElement('div');
        container.appendChild(toastDiv);
        
        const toast = new Toast(toastDiv, {
            message,
            type,
            ...options
        });
        
        await toast.init();
        
        // Track active toasts
        if (!container._toasts) {
            container._toasts = [];
        }
        container._toasts.push(toast);
        
        // Limit visible toasts
        if (container._toasts.length > this.maxVisible) {
            const oldestToast = container._toasts.shift();
            if (oldestToast) {
                oldestToast.dismiss();
            }
        }
        
        // Remove from array when destroyed
        toast.element.addEventListener('destroyed', () => {
            const index = container._toasts.indexOf(toast);
            if (index > -1) {
                container._toasts.splice(index, 1);
            }
        });
        
        return toast;
    }

    /**
     * Static convenience methods
     */
    success(message, options = {}) {
        return this.show(message, 'success', options);
    }

    error(message, options = {}) {
        return this.show(message, 'error', { duration: 5000, ...options });
    }

    warning(message, options = {}) {
        return this.show(message, 'warning', options);
    }

    info(message, options = {}) {
        return this.show(message, 'info', options);
    }

    /**
     * Clear all toasts
     */
    clearAll() {
        Object.values(this.containers).forEach(container => {
            if (container._toasts) {
                container._toasts.forEach(toast => toast.dismiss());
                container._toasts = [];
            }
        });
    }
}
