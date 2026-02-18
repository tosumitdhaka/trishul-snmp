# Changelog

All notable changes to Trishul-SNMP will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.2.3] - 2026-02-18

### Added
- **Phase 9 — WebSocket server-push backend** — `core/ws_manager.py` `ConnectionManager` singleton + asyncio UDP listener on `127.0.0.1:19876` for worker IPC. `/api/ws` endpoint with token auth, `full_state` on connect, ping/pong keepalive. Closes [#16](https://github.com/tosumitdhaka/trishul-snmp/issues/16).
- **Phase 8 — Auto-start on boot** — `AUTO_START_SIMULATOR` / `AUTO_START_TRAP_RECEIVER` env vars; FastAPI lifespan handler starts both services on container startup. Closes [#15](https://github.com/tosumitdhaka/trishul-snmp/issues/15).
- **Phase 2 — Global stats** — `core/stats_store.py` file-backed thread-safe JSON stats store; `/api/stats/`, `/api/stats/{module}`, `DELETE /api/stats/` endpoints. Closes [#11](https://github.com/tosumitdhaka/trishul-snmp/issues/11).
- **Phase 4–7 — Per-module stats** — walker (`walks_executed`, `walks_failed`, `oids_returned`), simulator (`start_count`, `restart_count`, `simulator_run_seconds`, `snmp_requests_served`), traps (`receiver_start_count`, `traps_received_total`, `traps_sent_total`), MIBs (`upload_count`, `delete_count`, `reload_count`). Closes [#14](https://github.com/tosumitdhaka/trishul-snmp/issues/14).

### Changed
- **Phase 9** — simulator and trap manager lifecycle endpoints broadcast `status` + `stats` WS events after state changes. `trap_receiver` worker sends UDP datagram to main process on each received trap.
- **Phase 8 — nginx.conf** — added `/api/ws` WS location block (3600s timeout), `proxy_redirect`, gzip compression, real-IP headers, 120s proxy timeouts (fixes 504 on large MIB reloads).
- **Phase 8 — docker-compose.yml** — removed deprecated `version: '3.8'`; backend healthcheck added; frontend `depends_on` uses `service_healthy`; `AUTO_START_*` env vars injected.
- **Phase 1** — `core/logging.py` renamed to `core/log_config.py` to stop shadowing stdlib `logging` (BUG-14). CORS `allow_origins` now reads `ALLOWED_ORIGINS` env var instead of wildcard (BUG-16).
- **Docker base image** — `python:3.9-slim` → `python:3.10-slim` (required for `str | None` type hint syntax).
- **UI/UX consistency** — unified dark card headers (`#1e293b`), consistent `card-header` height, standardised `btn-sm` / `btn-group-sm` across all pages, CSS height variables replacing magic numbers.
- **Dashboard tool cards** — horizontal layout, responsive breakpoints (`col-12 col-sm-6 col-md-3`), compact icon/text side-by-side.

### Fixed
- **Docker healthcheck** — replaced `curl` (absent in `python:3.10-slim`) with `python -c urllib.request.urlopen(...)`, fixing backend always-unhealthy state that blocked frontend startup.
- **Phase 1 — Auth** — `AppMeta` reads from settings instance (BUG-3); SHA-256+salt password hashing with plaintext migration on login (BUG-4); `SESSION_TIMEOUT` enforced (BUG-5); logout correctly passes token header (BUG-11); duplicate `SECRETS_FILE` definition removed (BUG-15).
- **Phase 3 — Dead code** — removed `api/routers/files.py` (never registered, imported non-existent `file_service.py`). Closes [#12](https://github.com/tosumitdhaka/trishul-snmp/issues/12).
- **Phase 4 — Walker** — input validation before walk (BUG-6); `HTTPException` caught before outer `except` to prevent message corruption (BUG-7); label-only walk returns `mode:label` instead of silent empty (BUG-13).
- **Phase 5 — Simulator** — `SimulatorManager.restart()` now preserves `_port`/`_community` (BUG-8); single restart code path via `_restart_simulator_with_stats()` helper (BUG-12); removed `simulator_metrics.json`.
- **Phase 6 — Traps** — `get_status()` uses `self._port` not hardcoded 1162 (BUG-9); `clear_traps()` uses context manager (BUG-10); `SnmpEngine` singleton in traps router (BUG-17).
- **Phase 7 — MIBs** — filename sanitization in `save_mib_file()` (IMPR-11).
- **Phase 8 — Restart chain stats** — `update_custom_data()` and MIB-reload-triggered restarts use `_restart_simulator_with_stats()`, fixing `restart_count` not incrementing on indirect restarts.
- **JS visibility bugs** — standardised all `style.display` toggles to `classList`/`d-none` across `traps.js`, `mibs.js`, `walker.js`, `browser.js`, `settings.js`; fixed walker `clearResults()` missing implementation; fixed walker history delete navigating to dashboard (`preventDefault` added).
- **Trap modal copy** — `showTrapDetails()` stores JSON in `_modalJson` keyed by modal ID; no raw JSON embedded in HTML `onclick` attributes.
- **Browser clear icon** — fixed `#btn-clear-search` always hidden when OID pre-loaded from other pages.

### Performance
- **WebSocket push** — eliminates dashboard (30s × 3), simulator (10s × 1), and traps (3s × 2) polling intervals. Frontend migration tracked in separate branch.

---

## [1.2.2] - 2026-02-18

### Added
- **Walk & Parse** - Added a clearer empty-state placeholder for "Current Result" when no results are present.

### Fixed
- **Walker** - Implemented missing "Clear results" handler and fixed delete-history click causing unintended navigation.
- **Traps** - Fixed trap detail modal "Copy" breaking due to JSON quotes in inline handlers; ensured row action buttons don't submit forms unintentionally (added `type="button"`).
- **Browser** - Fixed search clear icon visibility/state issues and standardized visibility toggling using class-based approach.
- **MIB Manager / Settings / UI** - Standardized dynamic show/hide behavior to use `classList` (`d-none`) instead of inline `style.display` where it was causing visibility bugs.

### Changed
- **UI/UX Consistency** - Unified card headers (dark theme, consistent height/alignment), standardized button sizing, and made card borders more visible across pages.


## [1.2.1] - 2026-02-11

### Added
- **Simulator** - Runtime metrics (uptime, SNMP request count, relative last activity).
- **Simulator** - Activity log persistence + search/filter/export, plus improved feedback (log + toast style messaging).
- **Simulator** - JSON validation + unsaved changes indicator / warning.

### Changed
- **Simulator** - Improved state management and UX while running (config lock/disable patterns).

### Fixed
- **Simulator** - More robust error handling for start/stop/restart/status flows.


## [1.2.0] - 2026-02-09

### Added
- **MIB Browser** - Interactive tree explorer with dual view modes (by module/OID hierarchy)
- **Tree Navigation** - Expandable OID hierarchy with configurable depth (1-5 levels, default: 3)
- **Real-time Search** - Find OIDs by name, numeric OID, or description with 500ms debounce
- **Smart Filtering** - Filter by module and object type (scalars, tables, columns, notifications)
- **Details Panel** - Compact metadata display with breadcrumb navigation
- **Seamless Integration** - Jump to Walker/Trap Sender with pre-filled data
- **State Persistence** - Remembers filters, search, expanded nodes, and selected OID across page switches
- **System MIB Detection** - Visual distinction between loaded MIBs (blue) and built-in MIBs (gray)
- **Trap Library Enhancement** - Shows all 24 traps (19 from loaded MIBs + 5 from system MIBs)
- **Dashboard Card** - Added MIB Browser card with purple theme
- **Depth Control** - Dropdown selector for expansion depth with expand/collapse buttons
- **Copy Buttons** - One-click copy for OID and full name in details panel
- **Loading Indicators** - Spinner and notifications for expand/collapse operations

### Fixed
- **Trap Count Consistency** - Dashboard, MIB Manager, and Browser now show consistent trap counts
- **MIB Delete Function** - Fixed error handling when deleting MIB files
- **State Restoration** - Fixed search clear icon visibility after page switch
- **Expanded State** - Tree expansion state now properly restored after navigation
- **Selected Node** - Details panel correctly loads after page switch
- **System MIB Badge** - SNMPv2-MIB and RMON-MIB correctly marked as system only when not loaded

### Changed
- **UI/UX Consistency** - Unified styling across all components
- **Trap Manager** - Renamed "Available Traps" to "Trap Library" for clarity
- **Dashboard Polling** - Reduced from 5s to 10s for better performance
- **Backend Caching** - Added 60-second cache for trap list API calls
- **Component Overview** - Updated README with compact overview of all 6 components

### Performance
- **Backend Caching** - Trap list cached for 60 seconds (reduces repeated queries)
- **Lazy Loading** - Tree nodes load children on-demand
- **Efficient Rendering** - Only visible nodes rendered in tree
- **Debounced Search** - 500ms delay prevents excessive API calls

---

## [1.1.7] - 2026-01-15

### Changed
- Rebranded to Trishul-SNMP
- Improved documentation and contributing guidelines

---

## [1.1.6] - 2025-12-20

### Added
- Docker volume support for data persistence
- Backup/restore functionality
- Smart GHCR authentication (public/private images)

---

## [1.1.5] - 2025-11-10

### Added
- One-command installer script
- Customizable backend and frontend ports
- Host network mode for dynamic SNMP ports

### Changed
- Improved UI
- Updated app icon

---

## [1.1.4] - 2025-10-05

### Changed
- Updated UI visuals and fixes

---

## [1.1.3] - 2025-09-15

### Added
- Enhanced trap management with real-time display
- JSON/CSV export for walk results

### Changed
- Improved error handling and logging

---

## [1.1.2] - 2025-08-20

### Added
- MIB browser with trap enumeration

### Fixed
- Trap sender fixes
- SNMP walker fixes

---

## [1.1.1] - 2025-07-10

### Fixed
- SNMP walk simulator fixes

---

## [1.0.0] - 2025-06-01

### Added
- Initial release
- SNMP simulator with custom OIDs
- Walk & parse functionality
- Trap sender and receiver
- MIB manager with validation
- Session-based authentication
- Docker deployment
- Bootstrap 5 UI

---

## Legend

- **Added** - New features
- **Changed** - Changes in existing functionality
- **Deprecated** - Soon-to-be removed features
- **Removed** - Removed features
- **Fixed** - Bug fixes
- **Security** - Vulnerability fixes
- **Performance** - Performance improvements

---

[1.2.3]: https://github.com/tosumitdhaka/trishul-snmp/compare/v1.2.2...v1.2.3
[1.2.2]: https://github.com/tosumitdhaka/trishul-snmp/compare/v1.2.1...v1.2.2
[1.2.1]: https://github.com/tosumitdhaka/trishul-snmp/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/tosumitdhaka/trishul-snmp/compare/v1.1.7...v1.2.0
[1.1.7]: https://github.com/tosumitdhaka/trishul-snmp/compare/v1.1.6...v1.1.7
[1.1.6]: https://github.com/tosumitdhaka/trishul-snmp/compare/v1.1.5...v1.1.6
[1.1.5]: https://github.com/tosumitdhaka/trishul-snmp/compare/v1.1.4...v1.1.5
[1.1.4]: https://github.com/tosumitdhaka/trishul-snmp/compare/v1.1.3...v1.1.4
[1.1.3]: https://github.com/tosumitdhaka/trishul-snmp/compare/v1.1.2...v1.1.3
[1.1.2]: https://github.com/tosumitdhaka/trishul-snmp/compare/v1.1.1...v1.1.2
[1.1.1]: https://github.com/tosumitdhaka/trishul-snmp/compare/v1.0.0...v1.1.1
[1.0.0]: https://github.com/tosumitdhaka/trishul-snmp/releases/tag/v1.0.0
