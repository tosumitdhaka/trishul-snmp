const API_BASE = "/api";
const HTML_CACHE = {}; 
let currentModule = null; // Track active module for cleanup

window.AppState = {
    simulator: null,
    logs: []
};

document.addEventListener("DOMContentLoaded", () => {
    // 1. Sidebar Toggle
    const sidebarToggle = document.querySelector('#sidebarToggle');
    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', e => {
            e.preventDefault();
            document.body.classList.toggle('sb-sidenav-toggled');
        });
    }

    // 2. Health & Routing
    checkBackendHealth();
    window.addEventListener('hashchange', handleRouting);
    handleRouting(); 
});

async function handleRouting() {
    let moduleName = window.location.hash.substring(1) || 'dashboard';
    
    // 1. Cleanup Previous Module
    if (currentModule && typeof currentModule.destroy === 'function') {
        currentModule.destroy();
    }
    
    // 2. Update Sidebar Active State
    document.querySelectorAll('.list-group-item').forEach(el => {
        el.classList.remove('active');
        if(el.getAttribute('href') === `#${moduleName}`) el.classList.add('active');
    });

    // 3. Load Content
    await loadModule(moduleName);
}

async function loadModule(moduleName) {
    const container = document.getElementById("main-content");
    const title = document.getElementById("page-title");

    const titles = {
        'dashboard': 'System Overview',
        'simulator': 'Simulator Manager',
        'walker': 'Walk & Parse Studio',
        'files': 'File Manager',
        'settings': 'Settings'
    };
    title.textContent = titles[moduleName] || 'SNMP Studio';

    if (!HTML_CACHE[moduleName]) {
        try {
            container.innerHTML = '<div class="text-center mt-5"><div class="spinner-border text-primary"></div></div>';
            const res = await fetch(`${moduleName}.html`);
            if (!res.ok) throw new Error("Module not found");
            HTML_CACHE[moduleName] = await res.text();
        } catch (e) {
            container.innerHTML = `<div class="alert alert-danger">Error: ${e.message}</div>`;
            return;
        }
    }

    container.innerHTML = HTML_CACHE[moduleName];

    // 4. Initialize Logic
    const moduleMap = {
        'dashboard': window.DashboardModule,
        'simulator': window.SimulatorModule,
        'walker': window.WalkerModule,
        'files': window.FilesModule,
        'settings': window.SettingsModule
    };

    if (moduleMap[moduleName]) {
        currentModule = moduleMap[moduleName]; // Set active module
        if(typeof currentModule.init === 'function') {
            currentModule.init();
        }
    }
}

// ... (keep checkBackendHealth as is) ...
async function checkBackendHealth() {
    const badge = document.getElementById("backend-status");
    try {
        const res = await fetch(`${API_BASE}/meta`);
        await res.json();
        badge.className = "badge bg-success";
        badge.textContent = "Online";
    } catch (e) {
        badge.className = "badge bg-danger";
        badge.textContent = "Offline";
    }
}
