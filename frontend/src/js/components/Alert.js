/**
 * Alert Component
 * Dismissible alert messages
 */

import { Component, html } from '../core/component.js';

export class Alert extends Component {
    constructor(container, props = {}) {
        super(container, {
            type: 'info', // 'primary', 'secondary', 'success', 'danger', 'warning', 'info', 'light', 'dark'
            message: '',
            icon: null,
            dismissible: true,
            autoClose: 0, // milliseconds, 0 = no auto close
            ...props
        });
    }

    render() {
        const { type, message, icon, dismissible } = this.props;
        
        const iconMap = {
            success: 'fas fa-check-circle',
            danger: 'fas fa-exclamation-circle',
            warning: 'fas fa-exclamation-triangle',
            info: 'fas fa-info-circle'
        };
        
        const alertIcon = icon || iconMap[type] || '';
        
        return html`
            <div class="alert alert-${type} ${dismissible ? 'alert-dismissible fade show' : ''}" role="alert">
                ${alertIcon ? html`<i class="${alertIcon} me-2"></i>` : ''}
                ${message}
                ${dismissible ? html`
                    <button type="button" class="btn-close" data-dismiss="alert"></button>
                ` : ''}
            </div>
        `;
    }

    async mounted() {
        if (this.props.dismissible) {
            this.on('click', '[data-dismiss="alert"]', () => {
                this.close();
            });
        }
        
        if (this.props.autoClose > 0) {
            setTimeout(() => {
                this.close();
            }, this.props.autoClose);
        }
    }

    close() {
        if (this.element) {
            this.element.classList.remove('show');
            setTimeout(() => {
                this.destroy();
            }, 150); // Bootstrap fade transition
        }
    }

    /**
     * Static helper to show quick alerts
     */
    static show(container, message, type = 'info', options = {}) {
        const alert = new Alert(container, {
            message,
            type,
            ...options
        });
        alert.init();
        return alert;
    }
}
