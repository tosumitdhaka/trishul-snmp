window.TrapsModule = {
    pollInterval: null,
    vbCount: 0,
    allTraps: [],
    allObjects: [],

    init: function() {
        this.checkStatus();
        this.loadTraps();
        this.pollInterval = setInterval(() => { this.checkStatus(); this.loadTraps(); }, 3000);
        
        this.loadTrapList();
        this.loadSelectedTrap();
    },

    destroy: function() {
        if (this.pollInterval) clearInterval(this.pollInterval);
    },

    loadTrapList: async function() {
        try {
            const res = await fetch('/api/mibs/traps');
            const data = await res.json();
            
            this.allTraps = data.traps;
            
            const select = document.getElementById('ts-trap-select');
            if (!select) return;
            
            select.innerHTML = '<option value="">-- Select a trap --</option>';
            
            data.traps.forEach(trap => {
                const option = document.createElement('option');
                option.value = trap.full_name;
                option.textContent = `${trap.full_name} (${trap.objects.length} objects)`;
                option.dataset.trap = JSON.stringify(trap);
                select.appendChild(option);
            });
        } catch (e) {
            console.error('Failed to load trap list:', e);
        }
    },

    onTrapSelected: function() {
        const select = document.getElementById('ts-trap-select');
        const selectedOption = select.options[select.selectedIndex];
        
        if (!selectedOption.value) return;
        
        try {
            const trap = JSON.parse(selectedOption.dataset.trap);
            this.populateTrapForm(trap);
        } catch (e) {
            console.error('Failed to parse trap data:', e);
        }
    },

    populateTrapForm: function(trap) {
        document.getElementById('ts-oid').value = trap.full_name;
        
        document.getElementById('vb-container').innerHTML = 
            '<div class="text-center text-muted small py-2" id="vb-empty" style="display:none;"></div>';
        
        this.addVarbind("SNMPv2-MIB::sysUpTime.0", "TimeTicks", "12345");
        
        if (trap.objects && trap.objects.length > 0) {
            trap.objects.forEach(obj => {
                let type = this.guessVarBindType(obj.name);
                this.addVarbind(obj.full_name, type, "");
            });
        }
        
        this.showNotification(`Loaded trap: ${trap.name}`, 'success');
    },

    guessVarBindType: function(name) {
        const lowerName = name.toLowerCase();
        
        if (lowerName.includes('index') || lowerName.includes('count') || lowerName.includes('number')) {
            return "Integer";
        } else if (lowerName.includes('status') || lowerName.includes('state') || lowerName.includes('admin')) {
            return "Integer";
        } else if (lowerName.includes('addr') || lowerName.includes('address')) {
            return "IpAddress";
        } else if (lowerName.includes('time') || lowerName.includes('tick')) {
            return "TimeTicks";
        } else if (lowerName.includes('counter')) {
            return "Counter";
        } else if (lowerName.includes('gauge') || lowerName.includes('speed') || lowerName.includes('bandwidth')) {
            return "Gauge";
        } else if (lowerName.includes('oid') || lowerName.includes('object')) {
            return "OID";
        }
        
        return "String";
    },

    showVarBindPicker: async function() {
        if (this.allObjects.length === 0) {
            try {
                const res = await fetch('/api/mibs/objects');
                const data = await res.json();
                this.allObjects = data.objects;
            } catch (e) {
                alert('Failed to load MIB objects');
                return;
            }
        }
        
        const modalHtml = `
            <div class="modal fade" id="varbindPickerModal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">Select VarBind from MIB</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <input type="text" id="vb-search" class="form-control mb-3" placeholder="Search objects...">
                            <div style="max-height: 400px; overflow-y: auto;">
                                <table class="table table-sm table-hover">
                                    <thead class="table-light sticky-top">
                                        <tr>
                                            <th>Object Name</th>
                                            <th>Module</th>
                                            <th>Type</th>
                                            <th></th>
                                        </tr>
                                    </thead>
                                    <tbody id="vb-picker-body"></tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        const existingModal = document.getElementById('varbindPickerModal');
        if (existingModal) existingModal.remove();
        
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        this.renderVarBindPicker(this.allObjects);
        
        document.getElementById('vb-search').addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase();
            const filtered = this.allObjects.filter(obj => 
                obj.name.toLowerCase().includes(query) || 
                obj.module.toLowerCase().includes(query)
            );
            this.renderVarBindPicker(filtered);
        });
        
        const modal = new bootstrap.Modal(document.getElementById('varbindPickerModal'));
        modal.show();
    },

    renderVarBindPicker: function(objects) {
        const tbody = document.getElementById('vb-picker-body');
        
        if (objects.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">No objects found</td></tr>';
            return;
        }
        
        tbody.innerHTML = objects.slice(0, 100).map(obj => `
            <tr>
                <td><code class="small">${obj.name}</code></td>
                <td><span class="badge bg-secondary small">${obj.module}</span></td>
                <td><span class="small">${obj.syntax}</span></td>
                <td>
                    <button class="btn btn-xs btn-primary" onclick="TrapsModule.addVarbindFromPicker('${obj.full_name}', '${obj.syntax}')">
                        <i class="fas fa-plus"></i>
                    </button>
                </td>
            </tr>
        `).join('');
        
        if (objects.length > 100) {
            tbody.innerHTML += `<tr><td colspan="4" class="text-center text-muted small">Showing first 100 results. Use search to narrow down.</td></tr>`;
        }
    },

    addVarbindFromPicker: function(fullName, syntax) {
        const type = this.syntaxToType(syntax);
        this.addVarbind(fullName, type, "");
        
        const modal = bootstrap.Modal.getInstance(document.getElementById('varbindPickerModal'));
        if (modal) modal.hide();
    },

    syntaxToType: function(syntax) {
        if (syntax.includes('Integer')) return 'Integer';
        if (syntax.includes('Counter64')) return 'Counter';
        if (syntax.includes('Counter')) return 'Counter';
        if (syntax.includes('Gauge')) return 'Gauge';
        if (syntax.includes('TimeTicks')) return 'TimeTicks';
        if (syntax.includes('IpAddress')) return 'IpAddress';
        if (syntax.includes('ObjectIdentifier')) return 'OID';
        return 'String';
    },

    loadSelectedTrap: function() {
        const trapData = sessionStorage.getItem('selectedTrap');
        if (!trapData) {
            this.addVarbind("SNMPv2-MIB::sysUpTime.0", "TimeTicks", "0");
            return;
        }

        try {
            const trap = JSON.parse(trapData);
            sessionStorage.removeItem('selectedTrap');
            
            const select = document.getElementById('ts-trap-select');
            if (select) {
                select.value = trap.full_name;
            }
            
            this.populateTrapForm(trap);
            
        } catch (e) {
            console.error('Failed to load selected trap:', e);
        }
    },

    showNotification: function(message, type = 'info') {
        const banner = document.createElement('div');
        banner.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
        banner.style.cssText = 'top: 80px; right: 20px; z-index: 9999; min-width: 300px;';
        banner.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        document.body.appendChild(banner);
        
        setTimeout(() => {
            banner.remove();
        }, 3000);
    },

    addVarbind: function(oid="", type="String", val="") {
        const container = document.getElementById("vb-container");
        const emptyMsg = document.getElementById("vb-empty");
        if (emptyMsg) emptyMsg.style.display = "none";
        
        const id = `vb-row-${this.vbCount++}`;
        const html = `
            <div class="card mb-2 border-secondary" id="${id}">
                <div class="card-body p-2">
                    <div class="input-group input-group-sm mb-1">
                        <span class="input-group-text bg-light">OID</span>
                        <input type="text" class="form-control vb-oid" value="${oid}" placeholder="1.3.6... or IF-MIB::ifIndex">
                        <button class="btn btn-outline-danger" type="button" onclick="document.getElementById('${id}').remove()">X</button>
                    </div>
                    <div class="input-group input-group-sm">
                        <select class="form-select vb-type" style="max-width: 120px;">
                            <option value="String" ${type==='String'?'selected':''}>String</option>
                            <option value="Integer" ${type==='Integer'?'selected':''}>Integer</option>
                            <option value="OID" ${type==='OID'?'selected':''}>OID</option>
                            <option value="TimeTicks" ${type==='TimeTicks'?'selected':''}>TimeTicks</option>
                            <option value="IpAddress" ${type==='IpAddress'?'selected':''}>IpAddress</option>
                            <option value="Counter" ${type==='Counter'?'selected':''}>Counter</option>
                            <option value="Gauge" ${type==='Gauge'?'selected':''}>Gauge</option>
                        </select>
                        <input type="text" class="form-control vb-val" value="${val}" placeholder="Value">
                    </div>
                </div>
            </div>
        `;
        container.insertAdjacentHTML('beforeend', html);
    },

    resetForm: function() {
        document.getElementById("vb-container").innerHTML = '<div class="text-center text-muted small py-2" id="vb-empty">No VarBinds added</div>';
        document.getElementById("ts-oid").value = "";
        
        const select = document.getElementById("ts-trap-select");
        if (select) select.value = "";
        
        this.addVarbind("SNMPv2-MIB::sysUpTime.0", "TimeTicks", "0");
    },

    sendTrap: async function(e) {
        e.preventDefault();
        const btn = e.target.querySelector("button[type='submit']");
        const originalText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sending...';

        try {
            // 1. Get trap OID and resolve if needed
            let trapOid = document.getElementById("ts-oid").value.trim();
            
            if (trapOid.includes("::")) {
                console.log(`[TRAP] Resolving trap OID: ${trapOid}`);
                const trapRes = await fetch(`/api/mibs/resolve?oid=${encodeURIComponent(trapOid)}&mode=numeric`);
                const trapData = await trapRes.json();
                trapOid = trapData.output;
                console.log(`[TRAP] Resolved to: ${trapOid}`);
            }

            // 2. Collect and resolve VarBinds
            const varbinds = [];
            const varbindRows = document.querySelectorAll("#vb-container .card");
            
            for (const row of varbindRows) {
                const oid = row.querySelector(".vb-oid").value.trim();
                const type = row.querySelector(".vb-type").value;
                const value = row.querySelector(".vb-val").value.trim();
                
                if (!oid || !value) continue;
                
                let numericOid = oid;
                if (oid.includes("::")) {
                    console.log(`[VARBIND] Resolving: ${oid}`);
                    const vbRes = await fetch(`/api/mibs/resolve?oid=${encodeURIComponent(oid)}&mode=numeric`);
                    const vbData = await vbRes.json();
                    numericOid = vbData.output;
                    console.log(`[VARBIND] Resolved to: ${numericOid}`);
                }
                
                varbinds.push({ oid: numericOid, type, value });
            }

            // 3. Build payload with NUMERIC OIDs ONLY
            const payload = {
                target: document.getElementById("ts-target").value,
                port: parseInt(document.getElementById("ts-port").value),
                community: document.getElementById("ts-comm").value,
                oid: trapOid,  // MUST be numeric
                varbinds: varbinds  // All OIDs MUST be numeric
            };

            console.log('[TRAP] Sending payload:', JSON.stringify(payload, null, 2));

            const res = await fetch('/api/traps/send', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
            
            if (res.ok) {
                const data = await res.json();
                this.showNotification(`✓ Trap sent to ${data.target}:${data.port}`, 'success');
                
                if (payload.target === "127.0.0.1" || payload.target === "localhost") {
                    setTimeout(() => this.loadTraps(), 500); 
                }
            } else {
                const errorData = await res.json();
                const errorMsg = errorData.detail || 'Unknown error';
                alert(`Trap Send Failed\n\n${errorMsg}`);
            }
        } catch (e) {
            console.error('[TRAP] Send error:', e);
            alert(`Connection Failed\n\n${e.message}`);
        } finally {
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    },

    checkStatus: async function() {
        try {
            const res = await fetch('/api/traps/status');
            const data = await res.json();
            this.updateStatusUI(data);
        } catch(e) {
            console.error('Status check failed:', e);
        }
    },

    updateStatusUI: function(status) {
        const badge = document.getElementById("tr-status-badge");
        const btnStart = document.getElementById("btn-tr-start");
        const btnStop = document.getElementById("btn-tr-stop");
        
        if (!badge) return;
        
        if (status.running) {
            badge.className = "badge bg-success";
            badge.innerHTML = `RUNNING <span class="small">(${status.resolve_mibs ? 'Resolved' : 'Raw'})</span>`;
            btnStart.disabled = true;
            btnStop.disabled = false;
        } else {
            badge.className = "badge bg-secondary";
            badge.textContent = "STOPPED";
            btnStart.disabled = false;
            btnStop.disabled = true;
        }
    },

    startReceiver: async function() {
        const port = parseInt(document.getElementById("tr-port").value);
        const community = document.getElementById("tr-community").value;
        const resolve = document.getElementById("tr-resolve-toggle").checked;
        
        await fetch('/api/traps/start', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                port: port,
                community: community,
                resolve_mibs: resolve
            })
        });
        
        this.checkStatus();
    },

    stopReceiver: async function() {
        await fetch('/api/traps/stop', {method:'POST'});
        this.checkStatus();
    },

    loadTraps: async function() {
        const tbody = document.getElementById("tr-table-body");
        const countBadge = document.getElementById("tr-count-badge");
        
        if (!tbody) return;
        
        try {
            const res = await fetch('/api/traps/');
            const json = await res.json();
            
            if (json.data.length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted p-3">No traps received.</td></tr>';
                if (countBadge) countBadge.textContent = '0';
                return;
            }
            
            if (countBadge) countBadge.textContent = json.data.length;
            
            tbody.innerHTML = json.data.map(t => {
                let trapBadgeClass = 'bg-secondary';
                const trapType = t.trap_type || 'Unknown';
                
                if (trapType.toLowerCase().includes('up') || trapType.toLowerCase().includes('start')) {
                    trapBadgeClass = 'bg-success';
                } else if (trapType.toLowerCase().includes('down')) {
                    trapBadgeClass = 'bg-danger';
                } else if (trapType.toLowerCase().includes('auth') || trapType.toLowerCase().includes('fail')) {
                    trapBadgeClass = 'bg-warning text-dark';
                }
                
                return `
                    <tr>
                        <td class="small text-muted">${t.time_str}</td>
                        <td><code class="small">${t.source}</code></td>
                        <td>
                            <span class="badge ${trapBadgeClass}">${trapType}</span>
                        </td>
                        <td>
                            <div class="varbind-list">
                                ${t.varbinds.map(v => {
                                    if (v.oid.includes('1.3.6.1.6.3.1.1.4.1.0') || v.name.includes('snmpTrapOID')) {
                                        return '';
                                    }
                                    
                                    let displayName = v.oid;
                                    let nameClass = 'text-muted';
                                    
                                    if (t.resolved && v.resolved && v.name !== v.oid) {
                                        displayName = v.name;
                                        nameClass = 'text-primary fw-bold';
                                    }
                                    
                                    if (displayName.length > 40) {
                                        displayName = displayName.substring(0, 37) + '...';
                                    }
                                    
                                    return `
                                        <div class="d-flex justify-content-between align-items-start small mb-1 py-1 border-bottom">
                                            <span class="${nameClass} me-2" style="font-family: 'Courier New', monospace; font-size: 0.8rem;">
                                                ${displayName}
                                            </span>
                                            <span class="text-dark text-end" style="max-width: 200px; word-break: break-word;">
                                                ${v.value}
                                            </span>
                                        </div>
                                    `;
                                }).join('')}
                            </div>
                        </td>
                    </tr>
                `;
            }).join('');
        } catch(e) {
            console.error('Failed to load traps:', e);
        }
    },

    clearTraps: async function() {
        if (!confirm('Clear all received traps?')) return;
        
        await fetch('/api/traps/', {method:'DELETE'});
        this.loadTraps();
    }
};
