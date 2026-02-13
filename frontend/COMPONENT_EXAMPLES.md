# Component Usage Examples

Practical examples of using the component system in Trishul SNMP.

## Quick Start

```javascript
// Import components
import { Card } from './components/Card.js';
import { Table } from './components/Table.js';
import { Alert } from './components/Alert.js';
import { Modal } from './components/Modal.js';

// Create and initialize
const card = new Card('#container', { title: 'My Card' });
await card.init();
```

## Example 1: Dashboard Status Cards

```javascript
import { Card } from './components/Card.js';
import { Alert } from './components/Alert.js';

class SimulatorStatusCard extends Card {
    constructor(container, store) {
        super(container, {
            title: 'SNMP Simulator',
            icon: 'fas fa-server',
            subtitle: 'Device simulation',
            collapsible: true,
            actions: [
                {
                    label: 'Start',
                    icon: 'fas fa-play',
                    class: 'btn-sm btn-success',
                    onClick: () => this.start()
                },
                {
                    label: 'Stop',
                    icon: 'fas fa-stop',
                    class: 'btn-sm btn-danger',
                    onClick: () => this.stop()
                }
            ]
        }, store);
    }
    
    async mounted() {
        this.subscribe('simulator', (status) => {
            this.updateDisplay(status);
        });
        
        await this.refresh();
    }
    
    async refresh() {
        try {
            const response = await fetch('/api/simulator/status', {
                headers: { 'X-Auth-Token': this.store.get('token') }
            });
            const data = await response.json();
            
            this.updateDisplay(data);
            this.store.set('simulator', data);
        } catch (error) {
            this.setContent('<div class="alert alert-danger">Failed to load status</div>');
        }
    }
    
    updateDisplay(status) {
        const { running, device_count, uptime } = status;
        
        this.setContent(`
            <div class="row g-2">
                <div class="col-md-4">
                    <div class="text-center">
                        <h4 class="mb-0">${device_count}</h4>
                        <small class="text-muted">Devices</small>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="text-center">
                        <h4 class="mb-0">
                            <span class="badge bg-${running ? 'success' : 'danger'}">
                                ${running ? 'Running' : 'Stopped'}
                            </span>
                        </h4>
                        <small class="text-muted">Status</small>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="text-center">
                        <h4 class="mb-0">${uptime || '0s'}</h4>
                        <small class="text-muted">Uptime</small>
                    </div>
                </div>
            </div>
        `);
    }
    
    async start() {
        try {
            await fetch('/api/simulator/start', {
                method: 'POST',
                headers: { 'X-Auth-Token': this.store.get('token') }
            });
            
            Alert.show(this.element, 'Simulator started', 'success', { autoClose: 2000 });
            await this.refresh();
        } catch (error) {
            Alert.show(this.element, 'Failed to start simulator', 'danger');
        }
    }
    
    async stop() {
        const confirmed = await Modal.confirm(
            'Are you sure you want to stop the simulator?',
            'Stop Simulator'
        );
        
        if (!confirmed) return;
        
        try {
            await fetch('/api/simulator/stop', {
                method: 'POST',
                headers: { 'X-Auth-Token': this.store.get('token') }
            });
            
            Alert.show(this.element, 'Simulator stopped', 'success', { autoClose: 2000 });
            await this.refresh();
        } catch (error) {
            Alert.show(this.element, 'Failed to stop simulator', 'danger');
        }
    }
}

// In dashboard module
export class Dashboard {
    constructor(container, store) {
        this.container = container;
        this.store = store;
    }
    
    async init() {
        // Create status cards
        this.simulatorCard = new SimulatorStatusCard(
            this.container.querySelector('#simulator-status'),
            this.store
        );
        await this.simulatorCard.init();
    }
}
```

## Example 2: Device List with Table

```javascript
import { Card } from './components/Card.js';
import { Table } from './components/Table.js';
import { Modal } from './components/Modal.js';
import { Alert } from './components/Alert.js';

class DeviceListCard extends Card {
    constructor(container, store) {
        super(container, {
            title: 'Simulated Devices',
            icon: 'fas fa-network-wired',
            actions: [
                {
                    label: 'Add Device',
                    icon: 'fas fa-plus',
                    class: 'btn-sm btn-primary',
                    onClick: () => this.showAddModal()
                },
                {
                    label: 'Refresh',
                    icon: 'fas fa-sync',
                    class: 'btn-sm btn-outline-secondary',
                    onClick: () => this.refresh()
                }
            ]
        }, store);
    }
    
    async mounted() {
        // Create table
        this.table = new Table(this.$('[data-body]'), {
            columns: [
                { key: 'name', label: 'Device Name', sortable: true },
                { key: 'ip', label: 'IP Address', sortable: true },
                { key: 'community', label: 'Community', sortable: true },
                {
                    key: 'status',
                    label: 'Status',
                    sortable: true,
                    render: (status) => {
                        const color = status === 'active' ? 'success' : 'secondary';
                        return `<span class="badge bg-${color}">${status}</span>`;
                    }
                },
                {
                    key: 'actions',
                    label: 'Actions',
                    render: (_, row) => `
                        <div class="btn-group btn-group-sm">
                            <button class="btn btn-outline-primary" 
                                    onclick="window.editDevice(${row.id})">
                                <i class="fas fa-edit"></i>
                            </button>
                            <button class="btn btn-outline-danger" 
                                    onclick="window.deleteDevice(${row.id})">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    `
                }
            ],
            data: [],
            striped: true,
            hover: true,
            responsive: true,
            emptyMessage: 'No devices configured'
        });
        
        await this.table.init();
        await this.refresh();
        
        // Global functions for inline handlers
        window.editDevice = (id) => this.editDevice(id);
        window.deleteDevice = (id) => this.deleteDevice(id);
    }
    
    async refresh() {
        try {
            const response = await fetch('/api/simulator/devices', {
                headers: { 'X-Auth-Token': this.store.get('token') }
            });
            const data = await response.json();
            
            this.table.setData(data.devices || []);
        } catch (error) {
            Alert.show(this.element, 'Failed to load devices', 'danger');
        }
    }
    
    async showAddModal() {
        const modal = new Modal({
            title: 'Add SNMP Device',
            size: 'lg',
            content: `
                <form id="add-device-form">
                    <div class="mb-3">
                        <label class="form-label">Device Name</label>
                        <input type="text" class="form-control" name="name" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">IP Address</label>
                        <input type="text" class="form-control" name="ip" 
                               placeholder="192.168.1.1" required>
                    </div>
                    <div class="row">
                        <div class="col-md-6">
                            <div class="mb-3">
                                <label class="form-label">Community</label>
                                <input type="text" class="form-control" name="community" 
                                       value="public" required>
                            </div>
                        </div>
                        <div class="col-md-6">
                            <div class="mb-3">
                                <label class="form-label">Port</label>
                                <input type="number" class="form-control" name="port" 
                                       value="161" required>
                            </div>
                        </div>
                    </div>
                </form>
            `,
            buttons: [
                { label: 'Cancel', class: 'btn-secondary' },
                {
                    label: 'Add Device',
                    icon: 'fas fa-plus',
                    class: 'btn-primary',
                    onClick: async () => {
                        const form = document.getElementById('add-device-form');
                        if (!form.checkValidity()) {
                            form.reportValidity();
                            return false; // Prevent modal close
                        }
                        
                        const formData = new FormData(form);
                        const device = Object.fromEntries(formData);
                        
                        try {
                            await fetch('/api/simulator/devices', {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                    'X-Auth-Token': this.store.get('token')
                                },
                                body: JSON.stringify(device)
                            });
                            
                            await this.refresh();
                            Alert.show(
                                this.element,
                                'Device added successfully',
                                'success',
                                { autoClose: 2000 }
                            );
                            
                            return true; // Allow modal close
                        } catch (error) {
                            Alert.show(
                                modal.$('.modal-body'),
                                'Failed to add device',
                                'danger'
                            );
                            return false; // Prevent modal close
                        }
                    }
                }
            ]
        });
        
        await modal.init();
        modal.show();
    }
    
    async editDevice(id) {
        // Similar to showAddModal but with existing data
        console.log('Edit device:', id);
    }
    
    async deleteDevice(id) {
        const confirmed = await Modal.confirm(
            'Are you sure you want to delete this device?',
            'Confirm Deletion'
        );
        
        if (!confirmed) return;
        
        try {
            await fetch(`/api/simulator/devices/${id}`, {
                method: 'DELETE',
                headers: { 'X-Auth-Token': this.store.get('token') }
            });
            
            this.table.removeRow(id);
            Alert.show(
                this.element,
                'Device deleted',
                'success',
                { autoClose: 2000 }
            );
        } catch (error) {
            Alert.show(this.element, 'Failed to delete device', 'danger');
        }
    }
}
```

## Example 3: Form with Validation

```javascript
import { Component } from '../core/component.js';
import { Alert } from './Alert.js';

class DeviceForm extends Component {
    constructor(container, props, store) {
        super(container, props, store);
        this.state = {
            formData: props.initialData || {},
            errors: {},
            submitting: false
        };
    }
    
    render() {
        const { formData, errors, submitting } = this.state;
        
        return `
            <form data-device-form>
                <div class="mb-3">
                    <label class="form-label">Device Name *</label>
                    <input type="text" class="form-control ${errors.name ? 'is-invalid' : ''}" 
                           name="name" value="${formData.name || ''}" required>
                    ${errors.name ? `<div class="invalid-feedback">${errors.name}</div>` : ''}
                </div>
                
                <div class="mb-3">
                    <label class="form-label">IP Address *</label>
                    <input type="text" class="form-control ${errors.ip ? 'is-invalid' : ''}" 
                           name="ip" value="${formData.ip || ''}" required>
                    ${errors.ip ? `<div class="invalid-feedback">${errors.ip}</div>` : ''}
                </div>
                
                <button type="submit" class="btn btn-primary" ${submitting ? 'disabled' : ''}>
                    ${submitting ? '<span class="spinner-border spinner-border-sm me-2"></span>' : ''}
                    ${submitting ? 'Saving...' : 'Save Device'}
                </button>
            </form>
        `;
    }
    
    async mounted() {
        this.on('submit', '[data-device-form]', (e) => {
            e.preventDefault();
            this.handleSubmit();
        });
        
        this.on('input', 'input', (e) => {
            const { name, value } = e.target;
            this.setState({
                formData: { ...this.state.formData, [name]: value },
                errors: { ...this.state.errors, [name]: '' }
            });
        });
    }
    
    validate() {
        const { formData } = this.state;
        const errors = {};
        
        if (!formData.name || formData.name.trim() === '') {
            errors.name = 'Device name is required';
        }
        
        if (!formData.ip || !/^\d{1,3}(\.\d{1,3}){3}$/.test(formData.ip)) {
            errors.ip = 'Valid IP address is required';
        }
        
        this.setState({ errors });
        return Object.keys(errors).length === 0;
    }
    
    async handleSubmit() {
        if (!this.validate()) return;
        
        this.setState({ submitting: true });
        
        try {
            const response = await fetch('/api/simulator/devices', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Auth-Token': this.store.get('token')
                },
                body: JSON.stringify(this.state.formData)
            });
            
            if (!response.ok) throw new Error('Failed to save');
            
            Alert.show(this.container, 'Device saved successfully', 'success');
            this.emit('device:saved', { device: this.state.formData });
            
        } catch (error) {
            Alert.show(this.container, 'Failed to save device', 'danger');
        } finally {
            this.setState({ submitting: false });
        }
    }
}
```

## Tips & Best Practices

### 1. Always await init()
```javascript
const card = new Card('#container', props);
await card.init(); // Don't forget this!
```

### 2. Clean up in beforeUnmount()
```javascript
async beforeUnmount() {
    if (this.interval) {
        clearInterval(this.interval);
    }
    // Store subscriptions are auto-cleaned
}
```

### 3. Use event delegation
```javascript
// Good - delegates from component root
this.on('click', '.btn-delete', handler);

// Bad - direct binding (may not work after re-render)
this.$('.btn-delete').addEventListener('click', handler);
```

### 4. Emit custom events for communication
```javascript
// In child component
this.emit('data:changed', { newValue: 123 });

// In parent
this.element.addEventListener('data:changed', (e) => {
    console.log(e.detail.newValue);
});
```

### 5. Use static helpers for quick actions
```javascript
// Quick alerts
Alert.show('#container', 'Success!', 'success');

// Confirm dialogs
if (await Modal.confirm('Delete?')) {
    // proceed with deletion
}
```
