#!/bin/bash
# Fix Ollama on CPQD — runs via ch8 update cycle
# Restart Ollama service and configure OLLAMA_HOST=0.0.0.0
systemctl restart ollama 2>/dev/null || service ollama restart 2>/dev/null || true
sleep 3
systemctl is-active ollama && echo "Ollama OK" || echo "Ollama not running"
ss -tlnp | grep 11434 && echo "Port 11434 listening" || echo "Port 11434 not listening"
