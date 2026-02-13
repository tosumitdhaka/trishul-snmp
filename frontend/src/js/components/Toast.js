/**
 * Toast Component
 * Non-blocking notifications that auto-dismiss
 */

import { Component, html } from '../core/component.js';

export class Toast extends Component {
    constructor(props = {}) {
        super(document.body, {
            message: '',
            type: 'info', // 'success', 'danger', 'warning', 'info'
            duration: 3000, // ms, 0 = no auto-close
            position: 'top-right', // 'top-right', 'top-left', 'bottom-right', 'bottom-left', 'top-center', 'bottom-center'
            icon: null,
            ...props
        });
        
        this.timeout = null;
    }

    render() {
        const { message, type, icon } = this.props;
        
        const iconMap = {
            success: 'fas fa-check-circle',
            danger: 'fas fa-exclamation-circle',
            warning: 'fas fa-exclamation-triangle',
            info: 'fas fa-info-circle'
        };
        
        const toastIcon = icon || iconMap[type] || '';
        
        return html`
            <div class="toast-item toast-${type}" role="alert" data-toast>
                <div class="toast-content">
                    ${toastIcon ? html`<i class="${toastIcon} me-2"></i>` : ''}
                    <span>${message}</span>
                </div>
                <button class="toast-close" data-close aria-label="Close">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;
    }

    async mounted() {
        // Add to container
        const container = ToastContainer.getInstance();
        container.addToast(this.element);
        
        // Close button
        this.on('click', '[data-close]', () => {
            this.close();
        });
        
        // Auto-close
        if (this.props.duration > 0) {
            this.timeout = setTimeout(() => {
                this.close();
            }, this.props.duration);
        }
        
        // Animate in
        requestAnimationFrame(() => {
            this.element.classList.add('toast-show');
        });
    }

    close() {
        if (this.timeout) {
            clearTimeout(this.timeout);
        }
        
        this.element.classList.add('toast-hiding');
        
        setTimeout(() => {
            this.destroy();
        }, 300);
    }

    /**
     * Static helper to show toasts
     */
    static show(message, type = 'info', options = {}) {
        const toast = new Toast({
            message,
            type,
            ...options
        });
        toast.init();
        return toast;
    }

    static success(message, options = {}) {
        return Toast.show(message, 'success', options);
    }

    static error(message, options = {}) {
        return Toast.show(message, 'danger', options);
    }

    static warning(message, options = {}) {
        return Toast.show(message, 'warning', options);
    }

    static info(message, options = {}) {
        return Toast.show(message, 'info', options);
    }
}

/**
 * Toast Container - Singleton
 */
class ToastContainer {
    static instance = null;

    constructor() {
        this.container = this.createContainer();
    }

    static getInstance() {
        if (!ToastContainer.instance) {
            ToastContainer.instance = new ToastContainer();
        }
        return ToastContainer.instance;
    }

    createContainer() {
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'toast-container toast-top-right';
            document.body.appendChild(container);
        }
        return container;
    }

    addToast(toastElement) {
        this.container.appendChild(toastElement);
    }

    setPosition(position) {
        this.container.className = `toast-container toast-${position}`;
    }
}
