/**
 * Table Component
 * Reusable data table with sorting, pagination, and actions
 */

import { Component, html } from '../core/component.js';

export class Table extends Component {
    constructor(container, props = {}) {
        super(container, {
            columns: [], // Array of {key, label, sortable, render}
            data: [],
            striped: true,
            hover: true,
            bordered: false,
            small: false,
            responsive: true,
            emptyMessage: 'No data available',
            sortColumn: null,
            sortDirection: 'asc',
            ...props
        });
        
        this.state = {
            sortColumn: this.props.sortColumn,
            sortDirection: this.props.sortDirection,
            data: this.sortData(this.props.data)
        };
    }

    render() {
        const { columns, striped, hover, bordered, small, responsive, emptyMessage } = this.props;
        const { data, sortColumn, sortDirection } = this.state;
        
        const tableClasses = [
            'table',
            striped && 'table-striped',
            hover && 'table-hover',
            bordered && 'table-bordered',
            small && 'table-sm'
        ].filter(Boolean).join(' ');
        
        const tableHtml = html`
            <table class="${tableClasses}">
                <thead>
                    <tr>
                        ${columns.map(col => html`
                            <th ${col.sortable ? `data-sort="${col.key}"` : ''} 
                                style="${col.sortable ? 'cursor: pointer;' : ''}">
                                ${col.label}
                                ${col.sortable && sortColumn === col.key ? html`
                                    <i class="fas fa-sort-${sortDirection === 'asc' ? 'up' : 'down'} ms-1"></i>
                                ` : ''}
                            </th>
                        `).join('')}
                    </tr>
                </thead>
                <tbody>
                    ${data.length === 0 ? html`
                        <tr>
                            <td colspan="${columns.length}" class="text-center text-muted py-4">
                                <i class="fas fa-inbox fa-2x mb-2 d-block"></i>
                                ${emptyMessage}
                            </td>
                        </tr>
                    ` : data.map(row => html`
                        <tr data-row-id="${row.id || ''}">
                            ${columns.map(col => html`
                                <td>
                                    ${col.render ? col.render(row[col.key], row) : row[col.key] || ''}
                                </td>
                            `).join('')}
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
        
        return responsive ? html`<div class="table-responsive">${tableHtml}</div>` : tableHtml;
    }

    async mounted() {
        // Setup sort handlers
        this.props.columns.forEach(col => {
            if (col.sortable) {
                this.on('click', `[data-sort="${col.key}"]`, () => {
                    this.sort(col.key);
                });
            }
        });
    }

    sort(columnKey) {
        const { sortColumn, sortDirection } = this.state;
        
        let newDirection = 'asc';
        if (sortColumn === columnKey) {
            newDirection = sortDirection === 'asc' ? 'desc' : 'asc';
        }
        
        this.setState({
            sortColumn: columnKey,
            sortDirection: newDirection,
            data: this.sortData(this.state.data, columnKey, newDirection)
        });
    }

    sortData(data, column = this.state.sortColumn, direction = this.state.sortDirection) {
        if (!column) return data;
        
        return [...data].sort((a, b) => {
            const aVal = a[column];
            const bVal = b[column];
            
            if (aVal === bVal) return 0;
            
            const comparison = aVal > bVal ? 1 : -1;
            return direction === 'asc' ? comparison : -comparison;
        });
    }

    setData(newData) {
        this.setState({
            data: this.sortData(newData)
        });
    }

    addRow(row) {
        const newData = [...this.state.data, row];
        this.setData(newData);
    }

    removeRow(id) {
        const newData = this.state.data.filter(row => row.id !== id);
        this.setData(newData);
    }
}
