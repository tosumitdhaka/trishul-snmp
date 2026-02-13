/**
 * AuthManager - Handles authentication and session management
 */
export class AuthManager {
    constructor() {
        this.token = sessionStorage.getItem('snmp_token');
        this.user = sessionStorage.getItem('snmp_user');
    }

    /**
     * Check if user is authenticated
     */
    isAuthenticated() {
        return !!this.token;
    }

    /**
     * Get current token
     */
    getToken() {
        return this.token;
    }

    /**
     * Get current user
     */
    getUser() {
        return this.user;
    }

    /**
     * Login with credentials
     */
    async login(username, password) {
        try {
            const response = await fetch('/api/settings/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ username, password })
            });

            const data = await response.json();

            if (response.ok) {
                this.token = data.token;
                this.user = data.username;
                
                sessionStorage.setItem('snmp_token', data.token);
                sessionStorage.setItem('snmp_user', data.username);
                
                console.log('[Auth] Login successful:', data.username);
                
                return {
                    success: true,
                    user: data.username
                };
            } else {
                console.error('[Auth] Login failed:', data.detail);
                
                return {
                    success: false,
                    error: data.detail || 'Login failed'
                };
            }
        } catch (error) {
            console.error('[Auth] Login error:', error);
            
            return {
                success: false,
                error: 'Connection error. Please check if backend is running.'
            };
        }
    }

    /**
     * Logout and clear session
     */
    async logout(callApi = true) {
        if (callApi) {
            try {
                await fetch('/api/settings/logout', {
                    method: 'POST',
                    headers: {
                        'X-Auth-Token': this.token
                    }
                });
            } catch (error) {
                console.error('[Auth] Logout API call failed:', error);
            }
        }

        this.token = null;
        this.user = null;
        
        sessionStorage.removeItem('snmp_token');
        sessionStorage.removeItem('snmp_user');
        
        console.log('[Auth] Logged out');
    }

    /**
     * Verify token is still valid
     */
    async verify() {
        if (!this.token) {
            return { valid: false };
        }

        try {
            const response = await fetch('/api/settings/check', {
                headers: {
                    'X-Auth-Token': this.token
                }
            });

            if (response.ok) {
                const data = await response.json();
                this.user = data.user;
                sessionStorage.setItem('snmp_user', data.user);
                
                return { valid: true, user: data.user };
            } else {
                this.logout(false);
                return { valid: false };
            }
        } catch (error) {
            console.error('[Auth] Token verification failed:', error);
            return { valid: false, error: error.message };
        }
    }
}
