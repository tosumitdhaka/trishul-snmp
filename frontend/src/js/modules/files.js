window.FilesModule = {
    init: function() {
        this.loadMibs();
        this.loadData();
    },

    loadMibs: async function() {
        const list = document.getElementById("mib-list");
        list.innerHTML = '<li class="list-group-item text-center">Loading...</li>';
        
        try {
            const res = await fetch('/api/files/mibs');
            const data = await res.json();
            
            list.innerHTML = "";
            if(data.mibs.length === 0) {
                list.innerHTML = '<li class="list-group-item text-center text-muted">No MIBs found</li>';
                return;
            }

            data.mibs.forEach(file => {
                const li = document.createElement("li");
                li.className = "list-group-item d-flex justify-content-between align-items-center";
                li.innerHTML = `
                    <span><i class="fas fa-file-alt text-secondary me-2"></i> ${file}</span>
                    <button class="btn btn-sm btn-outline-danger" onclick="FilesModule.deleteMib('${file}')">
                        <i class="fas fa-trash"></i>
                    </button>
                `;
                list.appendChild(li);
            });
        } catch (e) {
            list.innerHTML = '<li class="list-group-item text-danger">Error loading MIBs</li>';
        }
    },

    uploadMib: async function() {
        const input = document.getElementById("mib-upload-input");
        if (!input.files || input.files.length === 0) return;
        
        const btn = event.target;
        const originalText = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        btn.disabled = true;

        const formData = new FormData();
        // Loop and append all files with the key "files"
        for (let i = 0; i < input.files.length; i++) {
            formData.append("files", input.files[i]);
        }
        
        try {
            await fetch('/api/files/mibs', { method: "POST", body: formData });
            input.value = ""; 
            this.loadMibs();
        } catch (e) {
            alert("Upload failed");
        } finally {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    },

    deleteMib: async function(filename) {
        if(!confirm(`Delete ${filename}?`)) return;
        await fetch(`/api/files/mibs/${filename}`, { method: "DELETE" });
        this.loadMibs();
    },

    loadData: async function() {
        try {
            const res = await fetch('/api/files/data');
            const data = await res.json();
            document.getElementById("json-editor").value = JSON.stringify(data, null, 2);
        } catch(e) {
            document.getElementById("json-editor").value = "Error loading data";
        }
    },

    saveData: async function() {
        const content = document.getElementById("json-editor").value;
        try {
            const json = JSON.parse(content);
            const res = await fetch('/api/files/data', {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(json)
            });
            const data = await res.json();
            alert(data.message);
        } catch (e) {
            alert("Invalid JSON format!");
        }
    }
};
