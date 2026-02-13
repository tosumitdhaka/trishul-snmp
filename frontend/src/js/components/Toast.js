/**
 * Toast Notification Component
 * Non-blocking notifications with auto-dismiss and queue management
 */

import { Component, html } from '../core/component.js';

export class Toast extends Component {
    constructor(container, props = {}) {
        super(container, {
            message: '',
            type: 'info', // 'success', 'danger', 'warning', 'info'
            icon: null,
            duration: 3000, // milliseconds, 0 = no auto dismiss
            position: 'top-right', // 'top-right', 'top-left', 'bottom-right', 'bottom-left', 'top-center'
            dismissible: true,
            ...props
        });
        
        this.dismissTimeout = null;
    }

    render() {
        const { message, type, icon, dismissible } = this.props;
        
        const iconMap = {
            success: 'fas fa-check-circle',
            danger: 'fas fa-exclamation-circle',
            warning: 'fas fa-exclamation-triangle',
            info: 'fas fa-info-circle'
        };
        
        const toastIcon = icon || iconMap[type] || '';
        const bgClass = {
            success: 'bg-success',
            danger: 'bg-danger',
            warning: 'bg-warning',
            info: 'bg-info'
        }[type] || 'bg-info';
        
        return html`
            <div class="toast show ${bgClass} text-white" role="alert" data-toast>
                <div class="d-flex align-items-center p-3">
                    ${toastIcon ? html`
                        <i class="${toastIcon} me-3" style="font-size: 1.25rem;"></i>
                    ` : ''}
                    <div class="flex-grow-1">
                        ${message}
                    </div>
                    ${dismissible ? html`
                        <button type="button" class="btn-close btn-close-white ms-3" 
                                data-dismiss="toast" aria-label="Close"></button>
                    ` : ''}
                </div>
            </div>
        `;
    }

    async mounted() {
        // Fade in animation
        requestAnimationFrame(() => {
            if (this.element) {
                this.element.style.opacity = '0';
                this.element.style.transform = 'translateX(100%)';
                this.element.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
                
                requestAnimationFrame(() => {
                    this.element.style.opacity = '1';
                    this.element.style.transform = 'translateX(0)';
                });
            }
        });
        
        // Setup dismiss button
        if (this.props.dismissible) {
            this.on('click', '[data-dismiss="toast"]', () => {
                this.dismiss();
            });
        }
        
        // Auto dismiss
        if (this.props.duration > 0) {
            this.dismissTimeout = setTimeout(() => {
                this.dismiss();
            }, this.props.duration);
        }
    }

    dismiss() {
        if (this.dismissTimeout) {
            clearTimeout(this.dismissTimeout);
        }
        
        if (this.element) {
            this.element.style.opacity = '0';
            this.element.style.transform = 'translateX(100%)';
            
            setTimeout(() => {
                this.destroy();
            }, 300);
        }
    }

    async beforeUnmount() {
        if (this.dismissTimeout) {
            clearTimeout(this.dismissTimeout);
        }
    }
}

/**
 * ToastContainer - Manages multiple toasts
 */
export class ToastContainer {
    constructor(position = 'top-right') {
        this.position = position;
        this.container = null;
        this.toasts = [];
        this.init();
    }

    init() {
        // Create container if it doesn't exist
        this.container = document.getElementById('toast-container');
        
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.id = 'toast-container';
            this.container.className = `toast-container position-fixed p-3 ${this.getPositionClass()}`;
            this.container.style.zIndex = '9999';
            document.body.appendChild(this.container);
        }
    }

    getPositionClass() {
        const positions = {
            'top-right': 'top-0 end-0',
            'top-left': 'top-0 start-0',
            'bottom-right': 'bottom-0 end-0',
            'bottom-left': 'bottom-0 start-0',
            'top-center': 'top-0 start-50 translate-middle-x'
        };
        return positions[this.position] || positions['top-right'];
    }

    async show(message, type = 'info', options = {}) {
        const toastEl = document.createElement('div');
        toastEl.style.marginBottom = '0.5rem';
        this.container.appendChild(toastEl);
        
        const toast = new Toast(toastEl, {
            message,
            type,
            ...options
        });
        
        await toast.init();
        this.toasts.push(toast);
        
        // Remove from array when destroyed
        toast.element.addEventListener('DOMNodeRemoved', () => {
            const index = this.toasts.indexOf(toast);
            if (index > -1) {
                this.toasts.splice(index, 1);
            }
        });
        
        return toast;
    }

    clear() {
        this.toasts.forEach(toast => toast.dismiss());
        this.toasts = [];
    }
}

// Global toast instance
let globalToastContainer = null;

/**
 * Global toast helper
 */
export const toast = {
    success: (message, options = {}) => {
        if (!globalToastContainer) {
            globalToastContainer = new ToastContainer();
        }
        return globalToastContainer.show(message, 'success', options);
    },
    
    error: (message, options = {}) => {
        if (!globalToastContainer) {
            globalToastContainer = new ToastContainer();
        }
        return globalToastContainer.show(message, 'danger', options);
    },
    
    warning: (message, options = {}) => {
        if (!globalToastContainer) {
            globalToastContainer = new ToastContainer();
        }
        return globalToastContainer.show(message, 'warning', options);
    },
    
    info: (message, options = {}) => {
        if (!globalToastContainer) {
            globalToastContainer = new ToastContainer();
        }
        return globalToastContainer.show(message, 'info', options);
    },
    
    show: (message, type = 'info', options = {}) => {
        if (!globalToastContainer) {
            globalToastContainer = new ToastContainer();
        }
        return globalToastContainer.show(message, type, options);
    },
    
    clear: () => {
        if (globalToastContainer) {
            globalToastContainer.clear();
        }
    },
    
    setPosition: (position) => {
        globalToastContainer = new ToastContainer(position);
    }
};

// Make available globally
window.toast = toast;
