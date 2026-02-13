module.exports = {
  content: [
    "./src/**/*.html",
    "./src/js/**/*.js"
  ],
  darkMode: ["class", "[data-theme='dark']"],
  safelist: [
    // Background colors
    'bg-bg-primary',
    'bg-bg-secondary',
    'bg-bg-tertiary',
    'bg-bg-elevated',
    'bg-bg-hover',
    // Text colors
    'text-text-primary',
    'text-text-secondary',
    'text-text-tertiary',
    'text-text-muted',
    // Border colors
    'border-border-default',
    'border-border-subtle',
    'border-border-strong',
    // Status colors
    'text-status-online',
    'text-status-offline',
    'text-status-warning',
    'bg-status-online',
    'bg-status-offline',
    'bg-status-warning',
    // Accent colors
    'text-accent-primary',
    'text-accent-secondary',
    'text-accent-danger',
    'bg-accent-primary',
    'bg-accent-secondary',
    'bg-accent-danger',
    // Buttons
    'btn',
    'btn-primary',
    'btn-secondary',
    'btn-ghost',
    'btn-danger',
    'btn-sm',
    'btn-lg',
    // Cards
    'card',
    'card-header',
    'card-body',
    'card-footer',
    // Badges
    'badge',
    'badge-online',
    'badge-offline',
    'badge-warning',
    'badge-unknown',
    'badge-primary',
    // Alerts
    'alert',
    'alert-success',
    'alert-danger',
    'alert-warning',
    'alert-info',
    // Layout
    'sidebar',
    'nav-item',
    'nav-item.active',
    'page-header',
    'content-area',
    'layout-with-sidebar'
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"]
      },
      colors: {
        // Background colors
        "bg-primary": "var(--bg-primary, #0f172a)",
        "bg-secondary": "var(--bg-secondary, #1e293b)",
        "bg-tertiary": "var(--bg-tertiary, #334155)",
        "bg-elevated": "var(--bg-elevated, #1e293b)",
        "bg-hover": "var(--bg-hover, #334155)",
        // Text colors
        "text-primary": "var(--text-primary, #f1f5f9)",
        "text-secondary": "var(--text-secondary, #cbd5e1)",
        "text-tertiary": "var(--text-tertiary, #94a3b8)",
        "text-muted": "var(--text-muted, #64748b)",
        // Border colors
        "border-default": "var(--border-default, #334155)",
        "border-subtle": "var(--border-subtle, #334155)",
        "border-strong": "var(--border-strong, #475569)",
        // Status colors
        "status-online": "var(--status-online, #22c55e)",
        "status-offline": "var(--status-offline, #ef4444)",
        "status-warning": "var(--status-warning, #f59e0b)",
        // Accent colors
        "accent-primary": "var(--accent-primary, #3b82f6)",
        "accent-primary-hover": "var(--accent-primary-hover, #2563eb)",
        "accent-secondary": "var(--accent-secondary, #6366f1)",
        "accent-danger": "var(--accent-danger, #ef4444)",
        // SNMP colors
        "snmp-get": "var(--snmp-get, #3b82f6)",
        "snmp-set": "var(--snmp-set, #f59e0b)",
        "snmp-trap": "var(--snmp-trap, #8b5cf6)",
        "snmp-walk": "var(--snmp-walk, #10b981)"
      },
      borderColor: {
        border: "var(--border-default, #334155)",
        "border-default": "var(--border-default, #334155)",
        "border-subtle": "var(--border-subtle, #334155)",
        "border-strong": "var(--border-strong, #475569)"
      }
    }
  },
  plugins: []
};
