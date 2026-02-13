/**
 * Skeleton Component
 * Loading placeholders for content
 */

import { Component, html } from '../core/component.js';

export class Skeleton extends Component {
    constructor(container, props = {}) {
        super(container, {
            type: 'text', // 'text', 'title', 'avatar', 'thumbnail', 'button', 'card'
            width: null,
            height: null,
            count: 1,
            animation: 'pulse', // 'pulse', 'wave', 'none'
            ...props
        });
    }

    render() {
        const { type, width, height, count, animation } = this.props;
        
        const skeletons = [];
        for (let i = 0; i < count; i++) {
            skeletons.push(this.renderSkeleton(type, width, height, animation));
        }
        
        return html`
            <div class="skeleton-wrapper">
                ${skeletons.join('')}
            </div>
        `;
    }

    renderSkeleton(type, width, height, animation) {
        const style = [];
        if (width) style.push(`width: ${width}`);
        if (height) style.push(`height: ${height}`);
        const styleAttr = style.length > 0 ? `style="${style.join('; ')}"` : '';
        
        const classes = [
            'skeleton',
            `skeleton-${type}`,
            animation !== 'none' ? `skeleton-${animation}` : ''
        ].filter(Boolean).join(' ');
        
        return html`<div class="${classes}" ${styleAttr}></div>`;
    }

    /**
     * Predefined skeleton layouts
     */
    static card(container) {
        return new Skeleton(container, {
            type: 'card'
        });
    }

    static text(container, count = 3) {
        return new Skeleton(container, {
            type: 'text',
            count
        });
    }

    static table(container, rows = 5) {
        const html = `
            <div class="skeleton-table">
                ${Array(rows).fill(0).map(() => `
                    <div class="skeleton-table-row">
                        <div class="skeleton skeleton-text skeleton-pulse"></div>
                        <div class="skeleton skeleton-text skeleton-pulse"></div>
                        <div class="skeleton skeleton-text skeleton-pulse"></div>
                    </div>
                `).join('')}
            </div>
        `;
        
        container.innerHTML = html;
    }
}
