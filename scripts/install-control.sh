#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# CH8 Control Server — Installation Script
#
# Installs the CH8 coordination plane (control server + dashboard).
# Run on the server that will manage all your nodes.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/main/scripts/install-control.sh | bash
#   # or
#   bash scripts/install-control.sh
# ─────────────────────────────────────────────────────────────────

set -euo pipefail

# Colors
R='\033[0m'; B='\033[1m'; RED='\033[0;31m'; GRN='\033[0;32m'
YEL='\033[1;33m'; BLU='\033[0;34m'; CYN='\033[0;36m'; DIM='\033[2m'

header() { echo -e "\n${BLU}${B}[$1]${R} $2"; }
ok()     { echo -e "  ${GRN}✓${R} $1"; }
warn()   { echo -e "  ${YEL}⚠${R} $1"; }
fail()   { echo -e "  ${RED}✗${R} $1"; }

echo -e "${CYN}${B}"
cat << 'LOGO'
   _____ _   _ ___     ____            _             _
  / ____| | | / _ \   / ___|___  _ __ | |_ _ __ ___ | |
 | |    | |_| | | |  | |   / _ \| '_ \| __| '__/ _ \| |
 | |___ |  _  | |_|  | |__| (_) | | | | |_| | | (_) | |
  \____|_| |_|\___/   \____\___/|_| |_|\__|_|  \___/|_|
      Control Server — Coordination Plane
LOGO
echo -e "${R}"

# ── Step 1: Prerequisites ─────────────────────────────────────────

header "1/6" "Checking prerequisites..."

# Docker
if command -v docker &>/dev/null; then
    DOCKER_VER=$(docker --version | grep -oP '\d+\.\d+' | head -1)
    ok "Docker ${DOCKER_VER}"
else
    fail "Docker not found"
    echo -e "    Install: ${CYN}https://docs.docker.com/engine/install/${R}"
    exit 1
fi

# Docker Compose
if docker compose version &>/dev/null; then
    ok "Docker Compose (plugin)"
elif command -v docker-compose &>/dev/null; then
    ok "Docker Compose (standalone)"
else
    fail "Docker Compose not found"
    echo -e "    Install: ${CYN}https://docs.docker.com/compose/install/${R}"
    exit 1
fi

# Git
if command -v git &>/dev/null; then
    ok "Git $(git --version | grep -oP '\d+\.\d+\.\d+')"
else
    fail "Git not found"
    echo -e "    Install: ${CYN}sudo apt install git${R}"
    exit 1
fi

# ── Step 2: Installation directory ────────────────────────────────

header "2/6" "Setting up installation directory..."

DEFAULT_DIR="/data/ch8-control"
read -p "  Install path [${DEFAULT_DIR}]: " INSTALL_DIR
INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_DIR}"

if [ -d "${INSTALL_DIR}/.git" ]; then
    ok "Repository exists at ${INSTALL_DIR}, pulling updates..."
    cd "$INSTALL_DIR"
    git pull origin main 2>/dev/null || git pull origin master 2>/dev/null || true
else
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone -b master https://github.com/hudsonrj/ch8-cluster-agent.git "$INSTALL_DIR" 2>/dev/null || {
        warn "Git clone failed, assuming local files exist"
    }
    cd "$INSTALL_DIR"
fi

ok "Installation directory: ${INSTALL_DIR}"

# ── Step 3: Domain configuration ─────────────────────────────────

header "3/6" "Configuring domain and HTTPS..."

DEFAULT_DOMAIN="control.ch8ai.com.br"
read -p "  Control server domain [${DEFAULT_DOMAIN}]: " DOMAIN
DOMAIN="${DOMAIN:-$DEFAULT_DOMAIN}"

# Check if nginx is installed (for reverse proxy + SSL)
if command -v nginx &>/dev/null; then
    ok "Nginx found — will configure reverse proxy"

    NGINX_CONF="/etc/nginx/sites-available/ch8-control"
    if [ ! -f "$NGINX_CONF" ]; then
        echo -e "  ${BLU}Creating nginx config...${R}"
        cat > "$NGINX_CONF" << NGINX_EOF
server {
    listen 80;
    server_name ${DOMAIN};

    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        # SSE support (for chat streaming)
        proxy_http_version 1.1;
        proxy_set_header Connection '';
        proxy_buffering off;
        proxy_cache off;
        chunked_transfer_encoding off;
        proxy_read_timeout 300s;
    }
}
NGINX_EOF
        ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/ 2>/dev/null || true
        nginx -t 2>/dev/null && systemctl reload nginx 2>/dev/null && ok "Nginx configured" || warn "Nginx config written but reload failed"
    else
        ok "Nginx config already exists"
    fi

    # SSL with certbot
    if command -v certbot &>/dev/null; then
        if [ ! -d "/etc/letsencrypt/live/${DOMAIN}" ]; then
            echo -e "  ${BLU}Requesting SSL certificate...${R}"
            certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email admin@${DOMAIN} 2>/dev/null && \
                ok "SSL certificate obtained" || warn "SSL setup failed — configure manually"
        else
            ok "SSL certificate exists"
        fi
    else
        warn "Certbot not found — install for HTTPS: sudo apt install certbot python3-certbot-nginx"
    fi
else
    warn "Nginx not found — the control server will be available on port 8081 only"
    echo -e "    For production, install nginx: ${CYN}sudo apt install nginx${R}"
fi

# ── Step 4: Docker Compose configuration ──────────────────────────

header "4/6" "Configuring Docker Compose..."

COMPOSE_FILE="${INSTALL_DIR}/docker-compose.yml"

# Write docker-compose.yml if it doesn't exist or update it
cat > "$COMPOSE_FILE" << COMPOSE_EOF
services:
  control-server:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: ch8-control
    ports:
      - "8081:8000"
    environment:
      - CH8_CONTROL_BASE_URL=https://${DOMAIN}
    volumes:
      - ch8-control-data:/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 5s
      retries: 3

volumes:
  ch8-control-data:
COMPOSE_EOF

ok "docker-compose.yml configured (domain: ${DOMAIN})"

# ── Step 5: Build and start ───────────────────────────────────────

header "5/6" "Building and starting control server..."

cd "$INSTALL_DIR"
docker compose build --quiet 2>&1 && ok "Docker image built" || { fail "Build failed"; exit 1; }
docker compose up -d 2>&1 && ok "Container started" || { fail "Start failed"; exit 1; }

# Wait for health
echo -e "  ${DIM}Waiting for server to be ready...${R}"
for i in $(seq 1 30); do
    if curl -sf http://127.0.0.1:8081/health >/dev/null 2>&1; then
        ok "Server is healthy"
        break
    fi
    sleep 1
    [ "$i" -eq 30 ] && warn "Server not responding after 30s"
done

# ── Step 6: Generate bootstrap token ─────────────────────────────

header "6/6" "Generating bootstrap token..."

TOKEN_RESP=$(curl -sf -X POST "http://127.0.0.1:8081/api/admin/bootstrap?label=bootstrap&ttl_hours=8760" 2>/dev/null)
if [ -n "$TOKEN_RESP" ]; then
    TOKEN=$(echo "$TOKEN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])" 2>/dev/null)
    if [ -n "$TOKEN" ]; then
        ok "Bootstrap token created"
        echo ""
        echo -e "  ${B}Save this token — you'll need it to connect nodes:${R}"
        echo ""
        echo -e "    ${YEL}${B}${TOKEN}${R}"
        echo ""

        # Save to file
        TOKEN_FILE="${INSTALL_DIR}/.bootstrap-token"
        echo "$TOKEN" > "$TOKEN_FILE"
        chmod 600 "$TOKEN_FILE"
        ok "Token saved to ${TOKEN_FILE}"
    fi
else
    warn "Could not generate bootstrap token — do it manually:"
    echo -e "    curl -X POST http://127.0.0.1:8081/api/admin/bootstrap"
fi

# ── Done ──────────────────────────────────────────────────────────

echo ""
echo -e "${GRN}${B}╔═══════════════════════════════════════════════════════════╗${R}"
echo -e "${GRN}${B}║  CH8 Control Server — Installation Complete              ║${R}"
echo -e "${GRN}${B}╚═══════════════════════════════════════════════════════════╝${R}"
echo ""
echo -e "  ${B}Dashboard:${R}     https://${DOMAIN}"
echo -e "  ${B}Health:${R}        https://${DOMAIN}/health"
echo -e "  ${B}API Docs:${R}      https://${DOMAIN}/api/docs"
echo -e "  ${B}Container:${R}     docker logs ch8-control"
echo ""
echo -e "  ${B}Next steps:${R}"
echo -e "    1. Open the dashboard: ${CYN}https://${DOMAIN}${R}"
echo -e "    2. Install CH8 on your nodes:"
echo -e "       ${YEL}curl -fsSL https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/main/scripts/install-node.sh | bash${R}"
echo -e "    3. Connect each node:"
echo -e "       ${YEL}ch8 up --token ${TOKEN:-<YOUR_TOKEN>}${R}"
echo ""
