/**
 * Modal Component
 * Reusable modal dialog
 */

import { Component, html } from '../core/component.js';

export class Modal extends Component {
    constructor(props = {}) {
        // Modal doesn't need container - it appends to body
        super(document.body, {
            title: '',
            content: '',
            size: '', // '', 'sm', 'lg', 'xl'
            centered: true,
            scrollable: true,
            backdrop: true, // true, false, 'static'
            keyboard: true,
            buttons: [], // Array of {label, class, onClick}
            onShow: null,
            onHide: null,
            ...props
        });
        
        this.bsModal = null;
    }

    render() {
        const { title, content, size, centered, scrollable, buttons } = this.props;
        
        const sizeClass = size ? `modal-${size}` : '';
        const centeredClass = centered ? 'modal-dialog-centered' : '';
        const scrollableClass = scrollable ? 'modal-dialog-scrollable' : '';
        
        return html`
            <div class="modal fade" tabindex="-1" data-modal>
                <div class="modal-dialog ${sizeClass} ${centeredClass} ${scrollableClass}">
                    <div class="modal-content">
                        ${title ? html`
                            <div class="modal-header">
                                <h5 class="modal-title">${title}</h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                            </div>
                        ` : ''}
                        
                        <div class="modal-body">
                            ${content}
                        </div>
                        
                        ${buttons.length > 0 ? html`
                            <div class="modal-footer">
                                ${buttons.map((btn, i) => html`
                                    <button type="button" 
                                            class="btn ${btn.class || 'btn-secondary'}" 
                                            data-button="${i}">
                                        ${btn.icon ? html`<i class="${btn.icon} me-1"></i>` : ''}
                                        ${btn.label}
                                    </button>
                                `).join('')}
                            </div>
                        ` : ''}
                    </div>
                </div>
            </div>
        `;
    }

    async mounted() {
        // Initialize Bootstrap modal
        const modalEl = this.$('[data-modal]');
        if (!modalEl) return;
        
        // Import Bootstrap Modal dynamically
        const bootstrap = window.bootstrap;
        if (!bootstrap) {
            console.error('[Modal] Bootstrap not found');
            return;
        }
        
        this.bsModal = new bootstrap.Modal(modalEl, {
            backdrop: this.props.backdrop,
            keyboard: this.props.keyboard
        });
        
        // Setup button handlers
        this.props.buttons.forEach((btn, i) => {
            this.on('click', `[data-button="${i}"]`, (e) => {
                if (btn.onClick) {
                    const result = btn.onClick(e, this);
                    // Auto close if onClick doesn't return false
                    if (result !== false) {
                        this.hide();
                    }
                } else {
                    this.hide();
                }
            });
        });
        
        // Setup lifecycle events
        modalEl.addEventListener('show.bs.modal', () => {
            if (this.props.onShow) this.props.onShow(this);
        });
        
        modalEl.addEventListener('hidden.bs.modal', () => {
            if (this.props.onHide) this.props.onHide(this);
            this.destroy();
        });
    }

    show() {
        if (this.bsModal) {
            this.bsModal.show();
        }
    }

    hide() {
        if (this.bsModal) {
            this.bsModal.hide();
        }
    }

    setContent(content) {
        const body = this.$('.modal-body');
        if (body) {
            body.innerHTML = content;
        }
    }

    /**
     * Static helper for confirm dialogs
     */
    static async confirm(message, title = 'Confirm') {
        return new Promise((resolve) => {
            const modal = new Modal({
                title,
                content: message,
                centered: true,
                buttons: [
                    {
                        label: 'Cancel',
                        class: 'btn-secondary',
                        onClick: () => resolve(false)
                    },
                    {
                        label: 'Confirm',
                        class: 'btn-primary',
                        onClick: () => resolve(true)
                    }
                ]
            });
            modal.init();
            modal.show();
        });
    }

    /**
     * Static helper for alert dialogs
     */
    static async alert(message, title = 'Alert') {
        return new Promise((resolve) => {
            const modal = new Modal({
                title,
                content: message,
                centered: true,
                buttons: [
                    {
                        label: 'OK',
                        class: 'btn-primary',
                        onClick: () => resolve(true)
                    }
                ]
            });
            modal.init();
            modal.show();
        });
    }
}
