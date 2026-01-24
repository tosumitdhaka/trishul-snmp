window.DashboardModule = {
    init: async function() {
        // Fetch Sim Status
        try {
            const resSim = await fetch('/api/simulator/status');
            const dataSim = await resSim.json();
            const simEl = document.getElementById("dash-sim-status");
            if(simEl) {
                simEl.textContent = dataSim.running ? "RUNNING" : "STOPPED";
                simEl.className = dataSim.running ? "text-success" : "text-danger";
            }
        } catch(e) {}

        // Fetch MIB Count
        try {
            const resMib = await fetch('/api/files/mibs');
            const dataMib = await resMib.json();
            const mibEl = document.getElementById("dash-mib-count");
            if(mibEl) mibEl.textContent = dataMib.mibs.length;
        } catch(e) {}
    }
};
