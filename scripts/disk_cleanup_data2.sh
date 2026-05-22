#!/bin/bash
# disk_cleanup_data2.sh — limpeza segura de /data2 sem derrubar containers
# KB: Runbook: Limpeza de Disco /data2 — Docker Containerd Corrompido (ID 622)
set -e

THRESHOLD=${1:-85}  # limpar se disco > X%

PCT=$(df /data2 | awk 'NR==2 {gsub("%","",$5); print $5}')
echo "[disk_cleanup] /data2 em ${PCT}% (threshold=${THRESHOLD}%)"

if [ "$PCT" -lt "$THRESHOLD" ]; then
    echo "[disk_cleanup] Abaixo do threshold — nada a fazer."
    exit 0
fi

FREED=0

# 1. Diretório Docker antigo (pre-migração)
DOCKER_ROOT=$(docker info 2>/dev/null | grep "Docker Root Dir" | awk '{print $NF}')
if [ -d /data2/docker ] && [ "$DOCKER_ROOT" != "/data2/docker" ]; then
    SIZE=$(du -sb /data2/docker 2>/dev/null | awk '{print $1}')
    echo "[disk_cleanup] Removendo /data2/docker antigo (${SIZE} bytes)..."
    rm -rf /data2/docker
    FREED=$((FREED + SIZE))
fi

# 2. Build cache Docker
echo "[disk_cleanup] Limpando build cache..."
docker builder prune -af 2>/dev/null || true

# 3. Dangling images, containers parados, networks — só se containerd saudável
if docker system df > /dev/null 2>&1; then
    echo "[disk_cleanup] Limpando imagens/containers dangling..."
    docker image prune -f 2>/dev/null || true
    docker container prune -f 2>/dev/null || true
    docker network prune -f 2>/dev/null || true
else
    echo "[disk_cleanup] AVISO: containerd com metadata corrompido — prune pulado."
    echo "[disk_cleanup] Ação necessária: ctr content gc OU janela de manutenção."
fi

PCT_AFTER=$(df /data2 | awk 'NR==2 {gsub("%","",$5); print $5}')
echo "[disk_cleanup] Concluído: /data2 agora em ${PCT_AFTER}%"
