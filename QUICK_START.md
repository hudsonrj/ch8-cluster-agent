# Quick Start - Deploy em 5 Minutos

Guia rápido para colocar o website CH8 Agent no ar em **ch8agent.ch8ai.com.br**

## 🚀 Passo 1: Rodar o Container (2 minutos)

```bash
# Clone ou atualize o repositório
cd /data/ch8-agent
git pull origin master

# Deploy do website
cd website
./deploy.sh
```

**Pronto!** Site rodando em: `http://localhost:8080`

## 🌐 Passo 2: Configurar DNS no Cloudflare (3 minutos)

### Opção A: Porta 8080 (Mais Simples)

1. **Acesse:** https://dash.cloudflare.com/
2. **Selecione:** Domínio `ch8ai.com.br`
3. **Menu:** DNS → Records
4. **Add record:**
   ```
   Type: A
   Name: ch8agent
   IPv4 address: 216.24.57.1
   Proxy status: DNS only (🔘 cinza)
   TTL: Auto
   ```
5. **Save**

**Resultado:** `http://ch8agent.ch8ai.com.br:8080` ✅

### Opção B: Porta 80 com HTTPS (Recomendado)

**1. Mudar porta do container:**

Edite `docker-compose.yml`:
```yaml
ports:
  - "80:80"  # Mude de 8080:80 para 80:80
```

**2. Restart container:**
```bash
docker compose down
docker compose up -d --build
```

**3. Cloudflare DNS:**
```
Type: A
Name: ch8agent
IPv4 address: 216.24.57.1
Proxy status: Proxied (🟠 laranja)
TTL: Auto
```

**Resultado:** `https://ch8agent.ch8ai.com.br` ✅ (HTTPS automático!)

## ✅ Verificar

```bash
# DNS propagou?
dig ch8agent.ch8ai.com.br

# Site está no ar?
curl -I http://ch8agent.ch8ai.com.br:8080
# ou
curl -I https://ch8agent.ch8ai.com.br
```

## 📋 Comandos Úteis

```bash
# Ver logs
docker compose logs -f

# Status
docker compose ps

# Restart
docker compose restart

# Parar
docker compose down

# Atualizar site
git pull origin master
./deploy.sh
```

## 🛡️ Configuração de Firewall

```bash
# Para porta 8080
sudo ufw allow 8080/tcp

# Para portas 80/443 (HTTP/HTTPS)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

## 🔍 Troubleshooting Rápido

### Container não inicia
```bash
docker compose logs
docker compose down
docker compose up -d --build
```

### Site não carrega
```bash
# Testar localmente
curl http://localhost:8080

# Verificar DNS
dig ch8agent.ch8ai.com.br

# Ver se porta está aberta
sudo netstat -tulpn | grep :8080
```

### Porta já em uso
```bash
# Ver o que está usando
sudo lsof -i :8080

# Usar outra porta (editar docker-compose.yml)
ports:
  - "8081:80"
```

## 📚 Documentação Completa

- **Docker Deploy:** `website/DOCKER_DEPLOY.md`
- **Deployment Geral:** `WEBSITE_DEPLOYMENT.md`
- **Cloudflare Pages:** `DEPLOY_CLOUDFLARE.md`

## ⚡ Resumo Visual

```
┌─────────────────────┐
│  1. Deploy Container │
│  ./deploy.sh        │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 2. Cloudflare DNS   │
│ A: ch8agent         │
│ → 216.24.57.1       │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ ✅ Site Online!     │
│ ch8agent.ch8ai.com.br│
└─────────────────────┘
```

---

**Tempo total:** 5 minutos
**Resultado:** Website profissional no ar com seu domínio! 🎉
