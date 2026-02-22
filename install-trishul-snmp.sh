#!/bin/bash
# install-trishul-snmp.sh - Deploy Trishul SNMP from GHCR
# Usage: ./install-trishul-snmp.sh [up|down|restart|pull|logs|logs-frontend|status|backup|restore]

set -e

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GHCR_USER="tosumitdhaka"
BACKEND_IMAGE="ghcr.io/${GHCR_USER}/trishul-snmp-backend:latest"
FRONTEND_IMAGE="ghcr.io/${GHCR_USER}/trishul-snmp-frontend:latest"
VOLUME_NAME="trishul-snmp-data"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-8080}"

# Scoped to port — no wildcard deletes  [fix #5]
NGINX_CONF_PATH="/tmp/trishul-nginx-${FRONTEND_PORT}.conf"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

# ---------------------------------------------------------------------------
# GHCR Auth
# ---------------------------------------------------------------------------
check_ghcr_login() {
    docker pull "$BACKEND_IMAGE" >/dev/null 2>&1
}

login_ghcr() {
    echo -e "${BLUE}🔐 Checking GHCR access...${NC}"
    if check_ghcr_login; then
        echo -e "${GREEN}✅ GHCR access OK${NC}"; return 0
    fi
    echo -e "${YELLOW}⚠️  Authentication required${NC}"
    if [ -n "$GHCR_TOKEN" ]; then
        echo -e "${BLUE}Using GHCR_TOKEN from environment...${NC}"
        echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin
    else
        echo ""
        echo -e "${BLUE}Enter GitHub PAT (or press Enter to skip):${NC}"
        read -r -s -p "Token: " token; echo ""
        [ -n "$token" ] && echo "$token" | docker login ghcr.io -u "$GHCR_USER" --password-stdin \
            || echo -e "${YELLOW}⚠️  Skipping login...${NC}"
    fi
    if check_ghcr_login; then
        echo -e "${GREEN}✅ GHCR login successful${NC}"
    else
        echo -e "${RED}❌ Failed to access images${NC}"; exit 1
    fi
}

pull_images() {
    login_ghcr
    echo "📥 Pulling images..."
    docker pull "$BACKEND_IMAGE"
    docker pull "$FRONTEND_IMAGE"
    echo -e "${GREEN}✅ Images pulled${NC}"
}

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
setup_environment() {
    if ! docker volume inspect "$VOLUME_NAME" >/dev/null 2>&1; then
        echo "📦 Creating Docker volume: $VOLUME_NAME"
        docker volume create "$VOLUME_NAME"
        echo -e "${GREEN}✅ Volume created${NC}"
    else
        echo -e "${GREEN}✅ Volume exists: $VOLUME_NAME${NC}"
    fi
}

write_nginx_conf() {
    cat > "$NGINX_CONF_PATH" << EOF
server {
    listen $FRONTEND_PORT;
    server_name localhost;
    client_max_body_size 50M;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files \$uri \$uri/ /index.html;
    }

    # WebSocket — must come before /api/ block  [fix #1]
    location /api/ws {
        proxy_pass http://localhost:$BACKEND_PORT;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    # REST API
    location /api/ {
        proxy_pass http://localhost:$BACKEND_PORT;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_connect_timeout 60s;
        proxy_read_timeout 120s;
    }

    location ~* \.html$ {
        add_header Cache-Control "no-store, no-cache, must-revalidate";
        expires off;
    }
}
EOF
    echo -e "${GREEN}✅ Nginx config written${NC}"
}

# ---------------------------------------------------------------------------
# Wait for backend before starting frontend  [fix #3]
# ---------------------------------------------------------------------------
wait_for_backend() {
    echo -n "⏳ Waiting for backend"
    local i=0
    while [ $i -lt 30 ]; do
        if python3 -c "
import urllib.request, sys
try:
    urllib.request.urlopen('http://localhost:${BACKEND_PORT}/health', timeout=2)
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
            echo -e " ${GREEN}ready!${NC}"; return 0
        fi
        echo -n "."; sleep 2; i=$((i + 1))
    done
    echo -e " ${YELLOW}timed out — starting frontend anyway${NC}"
}

# ---------------------------------------------------------------------------
# Container lifecycle
# ---------------------------------------------------------------------------
run_containers() {
    pull_images
    setup_environment
    write_nginx_conf

    echo "🚀 Starting containers..."
    echo "   Backend port:  $BACKEND_PORT"
    echo "   Frontend port: $FRONTEND_PORT"
    echo "   Data volume:   $VOLUME_NAME"

    docker run -d \
        --name trishul-snmp-backend \
        --network host \
        -v "$VOLUME_NAME:/app/data" \
        --restart unless-stopped \
        "$BACKEND_IMAGE" \
        uvicorn main:app --host 0.0.0.0 --port "$BACKEND_PORT"

    wait_for_backend   # [fix #3]

    docker run -d \
        --name trishul-snmp-frontend \
        --network host \
        -v "$NGINX_CONF_PATH:/etc/nginx/conf.d/default.conf:ro" \
        --restart unless-stopped \
        "$FRONTEND_IMAGE"

    echo ""
    echo -e "${GREEN}✅ Trishul SNMP is running!${NC}"
    echo ""
    echo "🌐 Frontend:  http://localhost:$FRONTEND_PORT"
    echo "🔧 Backend:   http://localhost:$BACKEND_PORT/docs"
    echo "📦 Volume:    $VOLUME_NAME"
    echo ""
    echo "Default login: admin / admin123"
    echo -e "${YELLOW}⚠️  Change the default password immediately in Settings!${NC}"
    echo ""
}

stop_containers() {
    echo "🛑 Stopping containers..."
    docker stop trishul-snmp-backend trishul-snmp-frontend 2>/dev/null || true
    docker rm   trishul-snmp-backend trishul-snmp-frontend 2>/dev/null || true
    rm -f "$NGINX_CONF_PATH"   # [fix #5] — scoped, not wildcard
    echo -e "${GREEN}✅ Containers stopped${NC}"
}

restart_containers() {
    stop_containers
    run_containers
}

# ---------------------------------------------------------------------------
# Logs  [fix #6 — added logs-frontend]
# ---------------------------------------------------------------------------
show_logs() {
    echo -e "${BLUE}📜 Backend logs (Ctrl+C to exit):${NC}"
    docker logs -f trishul-snmp-backend
}

show_frontend_logs() {
    echo -e "${BLUE}📜 Frontend (nginx) logs (Ctrl+C to exit):${NC}"
    docker logs -f trishul-snmp-frontend
}

# ---------------------------------------------------------------------------
# Status — includes image tags + live app version  [fix #7]
# ---------------------------------------------------------------------------
show_status() {
    echo "📊 Container status:"
    docker ps --filter "name=trishul-snmp" \
        --format "table {{.Names}}\t{{.Status}}\t{{.Image}}" 2>/dev/null || true
    echo ""
    echo "⚙️  Configuration:"
    echo "   Backend port:  $BACKEND_PORT"
    echo "   Frontend port: $FRONTEND_PORT"
    echo "   Data volume:   $VOLUME_NAME"
    if docker volume inspect "$VOLUME_NAME" >/dev/null 2>&1; then
        local mount_point
        mount_point=$(docker volume inspect "$VOLUME_NAME" --format '{{.Mountpoint}}')
        echo "   Volume path:   $mount_point"
    fi
    echo ""
    echo "🏷️  Running images:"
    docker inspect trishul-snmp-backend  --format "   Backend:  {{.Config.Image}}" 2>/dev/null || echo "   Backend:  not running"
    docker inspect trishul-snmp-frontend --format "   Frontend: {{.Config.Image}}" 2>/dev/null || echo "   Frontend: not running"
    local version
    version=$(python3 -c "
import urllib.request, json, sys
try:
    r = urllib.request.urlopen('http://localhost:${BACKEND_PORT}/api/meta', timeout=3)
    print(json.loads(r.read()).get('version', 'unknown'))
except Exception:
    print('unavailable')
" 2>/dev/null)
    echo "   App version:  $version"
}

# ---------------------------------------------------------------------------
# Backup / Restore  [fix #8 — restore stops containers first]
# ---------------------------------------------------------------------------
backup_data() {
    local backup_file="trishul-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
    echo "💾 Creating backup: $backup_file"
    docker run --rm \
        -v "$VOLUME_NAME:/data" \
        -v "$(pwd):/backup" \
        alpine tar czf "/backup/$backup_file" -C /data .
    echo -e "${GREEN}✅ Backup created: $backup_file${NC}"
}

restore_data() {
    local backup_file="$1"
    if [ -z "$backup_file" ]; then
        echo -e "${RED}Error: Backup file not specified${NC}"
        echo "Usage: $0 restore <backup-file.tar.gz>"; exit 1
    fi
    if [ ! -f "$backup_file" ]; then
        echo -e "${RED}Error: Backup file not found: $backup_file${NC}"; exit 1
    fi
    echo -e "${YELLOW}⚠️  Stopping containers before restore...${NC}"
    stop_containers
    echo "📥 Restoring from: $backup_file"
    docker run --rm \
        -v "$VOLUME_NAME:/data" \
        -v "$(pwd):/backup" \
        alpine sh -c "rm -rf /data/* && tar xzf /backup/$backup_file -C /data"
    echo -e "${GREEN}✅ Data restored${NC}"
    echo -e "${BLUE}💡 Run '$0 up' to restart.${NC}"
}

# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
case "${1:-up}" in
    up)             run_containers ;;
    down)           stop_containers ;;
    restart)        restart_containers ;;
    pull)           pull_images ;;
    logs)           show_logs ;;
    logs-frontend)  show_frontend_logs ;;
    status)         show_status ;;
    backup)         backup_data ;;
    restore)        restore_data "$2" ;;
    *)
        echo "Usage: $0 {up|down|restart|pull|logs|logs-frontend|status|backup|restore}"
        echo ""
        echo "Commands:"
        echo "  up             - Pull images and start containers"
        echo "  down           - Stop and remove containers"
        echo "  restart        - Stop then start containers"
        echo "  pull           - Pull latest images"
        echo "  logs           - Tail backend logs"
        echo "  logs-frontend  - Tail frontend (nginx) logs"
        echo "  status         - Show container status, image tags, app version"
        echo "  backup         - Backup data volume to tar.gz"
        echo "  restore        - Restore data from backup (stops containers first)"
        echo ""
        echo "Environment variables:"
        echo "  BACKEND_PORT   - Backend port (default: 8000)"
        echo "  FRONTEND_PORT  - Frontend port (default: 8080)"
        echo "  GHCR_TOKEN     - GitHub PAT (optional, for private images)"
        echo ""
        echo "Examples:"
        echo "  $0 up"
        echo "  $0 status"
        echo "  $0 backup"
        echo "  $0 restore trishul-backup-20260222-123456.tar.gz"
        echo "  FRONTEND_PORT=3000 $0 up"
        exit 1
        ;;
esac
