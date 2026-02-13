/**
 * ApiClient - Centralized API communication with automatic token injection
 */
export class ApiClient {
    constructor(baseURL = '/api') {
        this.baseURL = baseURL;
    }

    /**
     * Make HTTP request with automatic auth token injection
     */
    async request(endpoint, options = {}) {
        const token = sessionStorage.getItem('snmp_token');
        
        const headers = {
            'Content-Type': 'application/json',
            ...(token && { 'X-Auth-Token': token }),
            ...options.headers
        };

        const url = endpoint.startsWith('http') 
            ? endpoint 
            : `${this.baseURL}${endpoint}`;

        try {
            const response = await fetch(url, {
                ...options,
                headers
            });

            // Handle 401 Unauthorized
            if (response.status === 401 && !endpoint.includes('/login')) {
                console.warn('[API] Unauthorized - triggering logout');
                window.dispatchEvent(new CustomEvent('auth:unauthorized'));
                throw new Error('Unauthorized');
            }

            // Handle non-OK responses
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(
                    errorData.detail || 
                    errorData.message || 
                    `HTTP ${response.status}: ${response.statusText}`
                );
            }

            // Return parsed JSON
            return await response.json();
            
        } catch (error) {
            console.error(`[API] Request failed: ${endpoint}`, error);
            throw error;
        }
    }

    /**
     * GET request
     */
    async get(endpoint, options = {}) {
        return this.request(endpoint, {
            method: 'GET',
            ...options
        });
    }

    /**
     * POST request
     */
    async post(endpoint, data, options = {}) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(data),
            ...options
        });
    }

    /**
     * PUT request
     */
    async put(endpoint, data, options = {}) {
        return this.request(endpoint, {
            method: 'PUT',
            body: JSON.stringify(data),
            ...options
        });
    }

    /**
     * DELETE request
     */
    async delete(endpoint, options = {}) {
        return this.request(endpoint, {
            method: 'DELETE',
            ...options
        });
    }

    /**
     * Upload file(s)
     */
    async uploadFile(endpoint, file, additionalData = {}) {
        const token = sessionStorage.getItem('snmp_token');
        const formData = new FormData();
        
        if (file instanceof FileList) {
            Array.from(file).forEach((f, index) => {
                formData.append('files', f);
            });
        } else {
            formData.append('file', file);
        }

        // Add additional data
        Object.entries(additionalData).forEach(([key, value]) => {
            formData.append(key, value);
        });

        const response = await fetch(`${this.baseURL}${endpoint}`, {
            method: 'POST',
            headers: {
                ...(token && { 'X-Auth-Token': token })
            },
            body: formData
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Upload failed');
        }

        return await response.json();
    }
}
