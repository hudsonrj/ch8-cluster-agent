# Deploy do Website com Docker

Guia completo para rodar o CH8 Agent website em container Docker no seu servidor.

## 🐳 Pré-requisitos

```bash
# Verificar se Docker está instalado
docker --version

# Se não estiver instalado (Ubuntu/Debian):
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Instalar Docker Compose
sudo apt-get update
sudo apt-get install docker-compose-plugin

# Adicionar seu usuário ao grupo docker (opcional)
sudo usermod -aG docker $USER
# Fazer logout/login para aplicar
```

## 🚀 Deploy Rápido

### Método 1: Docker Compose (Recomendado)

```bash
# 1. Navegar para o diretório do website
cd /data/ch8-agent/website

# 2. Build e iniciar o container
docker-compose up -d --build

# 3. Verificar se está rodando
docker-compose ps

# 4. Ver logs
docker-compose logs -f
```

**Pronto!** Site rodando em: `http://SEU_IP:8080`

### Método 2: Docker direto

```bash
# Build da imagem
cd /data/ch8-agent/website
docker build -t ch8agent-website .

# Rodar container
docker run -d \
  --name ch8agent-website \
  --restart unless-stopped \
  -p 8080:80 \
  ch8agent-website

# Verificar
docker ps | grep ch8agent
```

## 🌐 Configurar DNS no Cloudflare

Agora vamos fazer `ch8agent.ch8ai.com.br` apontar para seu servidor.

### Opção A: Subdomain Direto (Sem Proxy)

**No Cloudflare DNS:**

1. Acesse: https://dash.cloudflare.com/
2. Selecione domínio: **ch8ai.com.br**
3. Menu **DNS** → **Records**
4. Clique **Add record**
5. Configure:
   ```
   Type: A
   Name: ch8agent
   IPv4 address: 216.24.57.1
   Proxy status: DNS only (🔘 cinza)
   TTL: Auto
   ```
6. **Save**

**Testar em 2-5 minutos:**
```bash
# Verificar DNS
dig ch8agent.ch8ai.com.br

# Testar site
curl http://ch8agent.ch8ai.com.br:8080
```

### Opção B: Com Proxy Cloudflare (Recomendado para HTTPS)

Se você quer usar a porta 80 padrão e ter HTTPS automático:

**1. Mudar porta no docker-compose.yml:**

```yaml
ports:
  - "80:80"  # Ao invés de 8080:80
```

**2. No Cloudflare DNS:**
```
Type: A
Name: ch8agent
IPv4 address: 216.24.57.1
Proxy status: Proxied (🟠 laranja)
TTL: Auto
```

**3. Restartar container:**
```bash
docker-compose down
docker-compose up -d
```

**Resultado:** `https://ch8agent.ch8ai.com.br` (HTTPS automático!)

## 🔒 Setup com SSL/HTTPS (Sem Cloudflare Proxy)

Se você não quer usar o proxy do Cloudflare mas quer HTTPS:

### Usando Let's Encrypt com Certbot

```bash
# 1. Instalar Certbot
sudo apt-get install certbot

# 2. Obter certificado
sudo certbot certonly --standalone -d ch8agent.ch8ai.com.br

# 3. Certificados ficam em:
# /etc/letsencrypt/live/ch8agent.ch8ai.com.br/fullchain.pem
# /etc/letsencrypt/live/ch8agent.ch8ai.com.br/privkey.pem
```

### Atualizar docker-compose.yml para HTTPS:

```yaml
version: '3.8'

services:
  ch8agent-website:
    image: nginx:alpine
    container_name: ch8agent-website
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./:/usr/share/nginx/html:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
      - ./nginx-ssl.conf:/etc/nginx/conf.d/default.conf:ro
    restart: unless-stopped
```

### Criar nginx-ssl.conf:

```nginx
server {
    listen 80;
    server_name ch8agent.ch8ai.com.br;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name ch8agent.ch8ai.com.br;

    ssl_certificate /etc/letsencrypt/live/ch8agent.ch8ai.com.br/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ch8agent.ch8ai.com.br/privkey.pem;

    root /usr/share/nginx/html;
    index index.html;

    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml image/svg+xml;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location ~* \.(css|js|jpg|jpeg|png|gif|svg|ico)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

## 🔄 Gerenciamento do Container

### Comandos Úteis

```bash
# Ver logs em tempo real
docker-compose logs -f

# Parar container
docker-compose stop

# Iniciar container
docker-compose start

# Reiniciar container
docker-compose restart

# Parar e remover
docker-compose down

# Rebuild após mudanças
docker-compose up -d --build

# Ver status
docker-compose ps

# Acessar shell do container
docker-compose exec ch8agent-website sh

# Ver uso de recursos
docker stats ch8agent-website
```

### Atualizar Site

```bash
# 1. Fazer mudanças nos arquivos HTML/CSS/JS
cd /data/ch8-agent/website

# 2. Rebuild e restart
docker-compose up -d --build

# 3. Verificar
docker-compose logs --tail=50
```

## 🛡️ Configuração de Firewall

Se usar firewall (UFW/iptables):

```bash
# Para porta 8080
sudo ufw allow 8080/tcp

# Para portas 80/443 (HTTP/HTTPS)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Verificar
sudo ufw status
```

## 📊 Monitoramento

### Ver Logs do Nginx

```bash
# Logs de acesso
docker-compose exec ch8agent-website tail -f /var/log/nginx/access.log

# Logs de erro
docker-compose exec ch8agent-website tail -f /var/log/nginx/error.log
```

### Healthcheck

Adicionar ao docker-compose.yml:

```yaml
services:
  ch8agent-website:
    # ... outras configs
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

### Monitoramento Externo

Use serviços como:
- UptimeRobot: https://uptimerobot.com/
- Pingdom: https://www.pingdom.com/
- StatusCake: https://www.statuscake.com/

## 🔧 Troubleshooting

### Container não inicia

```bash
# Ver logs de erro
docker-compose logs

# Verificar se porta está em uso
sudo netstat -tulpn | grep :8080

# Testar build
docker-compose build

# Limpar e rebuild
docker-compose down
docker system prune -a
docker-compose up -d --build
```

### Site não carrega

```bash
# 1. Verificar se container está rodando
docker-compose ps

# 2. Testar localmente
curl http://localhost:8080

# 3. Verificar DNS
dig ch8agent.ch8ai.com.br

# 4. Testar do servidor
curl http://216.24.57.1:8080

# 5. Ver logs
docker-compose logs -f
```

### Porta já em uso

```bash
# Ver o que está usando a porta
sudo lsof -i :8080

# Matar processo se necessário
sudo kill -9 <PID>

# Ou usar outra porta no docker-compose.yml
ports:
  - "8081:80"
```

## 🚀 Setup Completo em Produção

### Script de Deploy Automático

Crie `deploy.sh`:

```bash
#!/bin/bash
set -e

echo "🚀 Deploying CH8 Agent Website..."

# Pull latest changes
cd /data/ch8-agent
git pull origin master

# Build and restart container
cd website
docker-compose down
docker-compose up -d --build

# Wait for container to be healthy
sleep 5

# Check if running
if docker-compose ps | grep -q "Up"; then
    echo "✅ Deploy successful!"
    echo "🌐 Site available at: http://ch8agent.ch8ai.com.br:8080"
else
    echo "❌ Deploy failed!"
    docker-compose logs
    exit 1
fi
```

Tornar executável:
```bash
chmod +x deploy.sh
./deploy.sh
```

## 📋 Checklist de Deploy

- [ ] Docker e Docker Compose instalados
- [ ] Container buildado com sucesso
- [ ] Container rodando (`docker-compose ps`)
- [ ] Site acessível localmente (`curl localhost:8080`)
- [ ] Firewall configurado (porta 8080 ou 80/443)
- [ ] DNS no Cloudflare configurado (A record ou CNAME)
- [ ] DNS propagado (`dig ch8agent.ch8ai.com.br`)
- [ ] Site acessível externamente
- [ ] HTTPS configurado (se usando SSL)
- [ ] Certificado SSL válido (se aplicável)
- [ ] Auto-restart configurado (`restart: unless-stopped`)
- [ ] Logs verificados sem erros
- [ ] Monitoramento configurado

## 🎯 Resumo da Configuração

### Opção Simples (HTTP na porta 8080):

**Docker:**
```bash
cd /data/ch8-agent/website
docker-compose up -d --build
```

**Cloudflare DNS:**
```
Type: A
Name: ch8agent
IPv4: 216.24.57.1
Proxy: DNS only (cinza)
```

**Acesso:** http://ch8agent.ch8ai.com.br:8080

### Opção Completa (HTTPS na porta 443):

**Docker:**
```bash
# Editar docker-compose.yml: ports: - "80:80" - "443:443"
docker-compose up -d --build
```

**Cloudflare DNS:**
```
Type: A
Name: ch8agent
IPv4: 216.24.57.1
Proxy: Proxied (laranja) - HTTPS automático!
```

**Acesso:** https://ch8agent.ch8ai.com.br

---

**Tempo total de deploy:** 5-10 minutos
**Custo:** $0 (100% gratuito)
**Manutenção:** Mínima (container restart automático)
