/**
 * Card Component
 * Reusable card container with header, body, and footer
 */

import { Component, html } from '../core/component.js';

export class Card extends Component {
    constructor(container, props = {}) {
        super(container, {
            title: '',
            icon: '',
            subtitle: '',
            headerClass: 'bg-light',
            bodyClass: '',
            footerClass: '',
            collapsible: false,
            collapsed: false,
            actions: [], // Array of {label, icon, onClick, class}
            ...props
        });
        
        this.state = {
            collapsed: this.props.collapsed
        };
    }

    render() {
        const { title, icon, subtitle, headerClass, bodyClass, footerClass, collapsible, actions } = this.props;
        const { collapsed } = this.state;
        
        return html`
            <div class="card shadow-sm border-0 mb-3">
                ${title ? html`
                    <div class="card-header ${headerClass} d-flex align-items-center justify-content-between">
                        <div class="d-flex align-items-center">
                            ${icon ? html`<i class="${icon} me-2"></i>` : ''}
                            <div>
                                <h5 class="mb-0 fw-bold">${title}</h5>
                                ${subtitle ? html`<small class="text-muted">${subtitle}</small>` : ''}
                            </div>
                        </div>
                        <div class="d-flex align-items-center gap-2">
                            ${actions.map(action => html`
                                <button class="btn btn-sm ${action.class || 'btn-outline-secondary'}" 
                                        data-action="${action.label}">
                                    ${action.icon ? html`<i class="${action.icon}"></i>` : ''}
                                    ${action.label}
                                </button>
                            `).join('')}
                            ${collapsible ? html`
                                <button class="btn btn-sm btn-link text-decoration-none" 
                                        data-toggle="collapse">
                                    <i class="fas fa-chevron-${collapsed ? 'down' : 'up'}"></i>
                                </button>
                            ` : ''}
                        </div>
                    </div>
                ` : ''}
                
                <div class="card-body ${bodyClass}" style="${collapsed ? 'display: none;' : ''}" 
                     data-body>
                    ${this.props.content || ''}
                </div>
                
                ${this.props.footer ? html`
                    <div class="card-footer ${footerClass}">
                        ${this.props.footer}
                    </div>
                ` : ''}
            </div>
        `;
    }

    async mounted() {
        // Setup collapse toggle
        if (this.props.collapsible) {
            this.on('click', '[data-toggle="collapse"]', () => {
                this.toggleCollapse();
            });
        }
        
        // Setup action buttons
        this.props.actions.forEach(action => {
            this.on('click', `[data-action="${action.label}"]`, (e) => {
                if (action.onClick) {
                    action.onClick(e, this);
                }
            });
        });
    }

    toggleCollapse() {
        this.setState({ collapsed: !this.state.collapsed });
    }

    setContent(content) {
        const body = this.$('[data-body]');
        if (body) {
            body.innerHTML = content;
        }
    }
}
