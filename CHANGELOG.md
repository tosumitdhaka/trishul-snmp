# Changelog

All notable changes to Trishul-SNMP will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.3.0] - 2026-02-18

### Added
- **WebSocket server-push** (Phase 9) — replaces all frontend `setInterval` HTTP polling.
  Backend now pushes real-time state changes to all connected clients via a persistent
  WebSocket connection at `/api/ws`. Closes [#16](https://github.com/tosumitdhaka/trishul-snmp/issues/16).
- **`core/ws_manager.py`** — `ConnectionManager` singleton with `broadcast()`, `send_to()`,
  and dead-connection auto-cleanup. Module-level `manager` used by all routers.
- **`api/routers/ws.py`** — WebSocket endpoint `/api/ws` with `?token=` query-param auth
  (4001 close on failure). Sends `full_state` snapshot on connect; ping/pong keepalive.
- **UDP loopback IPC** — `_UDPListenerProtocol` in `ws_manager.py` listens on
  `127.0.0.1:WS_INTERNAL_PORT` (default 19876). Worker subprocesses send trap datagrams
  here for zero-latency real-time push without shared memory or Redis.
- **`workers/trap_receiver.py`** — `_send_ws_datagram()` sends `{type:"trap"}` UDP datagram
  to main process after every trap written to disk (fire-and-forget, non-fatal on failure).
- **Auto-start on boot** (Phase 8) — simulator and trap receiver start automatically on
  container startup via FastAPI lifespan handler. Controlled by `AUTO_START_SIMULATOR` and
  `AUTO_START_TRAP_RECEIVER` env vars.
- **`docs/websocket.md`** — full WebSocket API reference: message types, connection flow,
  keepalive, IPC architecture diagram, and `wscat` test commands.

### Changed
- **`api/routers/simulator.py`** — all lifecycle endpoints (`start`, `stop`, `restart`,
  `data`) now `await _broadcast_status()` + `await _broadcast_stats()` after state changes,
  pushing `{type:"status"}` and `{type:"stats"}` to WS clients.
- **`services/trap_manager.py`** — `start()` and `stop()` call `_try_broadcast_status()`
  (uses `asyncio.ensure_future` — safe from sync context). `--ws-port` now passed to
  `trap_receiver` subprocess from `settings.WS_INTERNAL_PORT`.
- **`main.py`** — lifespan starts UDP listener (`await start_udp_listener()`) **before**
  auto-starting services to prevent dropped datagrams on boot. Graceful
  `await stop_udp_listener()` on shutdown.
- **`nginx.conf`** — added `/api/ws` location block (before `/api/` catch-all) with
  `Upgrade`/`Connection` headers and `proxy_read_timeout 3600s` for persistent WS connections.
  Also added `proxy_redirect`, gzip compression, and real-IP forwarding headers (Phase 8).
- **`core/config.py`** — added `WS_INTERNAL_PORT`, `AUTO_START_SIMULATOR`,
  `AUTO_START_TRAP_RECEIVER` settings; `APP_AUTHOR` / `APP_DESCRIPTION` now read from env.
- **`.env`** — added `WS_INTERNAL_PORT=19876`, `AUTO_START_SIMULATOR=true`,
  `AUTO_START_TRAP_RECEIVER=true`.

### Fixed
- **Docker healthcheck** — replaced `curl` (not present in `python:3.10-slim`) with
  `python -c urllib.request.urlopen(...)`. This was causing the backend container to report
  unhealthy, which blocked frontend startup via `depends_on: condition: service_healthy`.
- **`simulator.py` restart stats** — `update_custom_data()` and `mibs.py` MIB-reload-triggered
  restarts now go through `_restart_simulator_with_stats()` shared helper, fixing
  `restart_count` not incrementing on indirect restarts.
- **`trap_manager.py` port** — `get_status()` now returns `self._port` instead of hardcoded
  `1162` (BUG-9).
- **`trap_manager.py` file handle** — `clear_traps()` uses context manager to prevent
  file handle leak (BUG-10).
- **Docker Compose** — removed deprecated `version: '3.8'` key; added backend healthcheck
  so frontend `depends_on: service_healthy` works correctly.
- **nginx** — added `proxy_connect_timeout 60s` / `proxy_send_timeout 120s` /
  `proxy_read_timeout 120s` to prevent 504 on large MIB reloads and SNMP walks.

### Performance
- **Zero polling** — WS push eliminates dashboard (30s×3 calls), simulator (10s×1),
  and traps (3s×2 calls) polling loops. Frontend integration tracked separately.

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

[1.3.0]: https://github.com/tosumitdhaka/trishul-snmp/compare/v1.2.2...v1.3.0
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
