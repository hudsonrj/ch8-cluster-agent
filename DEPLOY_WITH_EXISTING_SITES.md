# Deploy com Sites Existentes - Proxy Reverso

Guia para deploy do CH8 Agent website quando você já tem outros sites rodando no servidor.

## 🎯 Cenário

Você já tem:
- ✅ Nginx ou Apache rodando nas portas 80/443
- ✅ Outros sites configurados (ex: www.ch8ai.com.br)
- ✅ DNS do domínio ch8ai.com.br já configurado

Queremos adicionar: **ch8agent.ch8ai.com.br** rodando em container Docker

## 🐳 Passo 1: Rodar Container na Porta 8080 (2 minutos)

```bash
cd /data/ch8-agent/website

# Deploy do container (vai rodar na porta 8080)
./deploy.sh

# Verificar
docker compose ps
curl http://localhost:8080
```

✅ **Container rodando em localhost:8080**

## 🔀 Passo 2: Configurar Proxy Reverso (3 minutos)

### Opção A: Nginx (Recomendado)

**1. Copiar configuração:**
```bash
sudo cp /data/ch8-agent/website/nginx-proxy.conf /etc/nginx/sites-available/ch8agent.conf
```

**2. Habilitar site:**
```bash
sudo ln -s /etc/nginx/sites-available/ch8agent.conf /etc/nginx/sites-enabled/
```

**3. Testar configuração:**
```bash
sudo nginx -t
```

**4. Aplicar:**
```bash
sudo systemctl reload nginx
```

### Opção B: Apache

**1. Habilitar módulos necessários:**
```bash
sudo a2enmod proxy
sudo a2enmod proxy_http
sudo a2enmod headers
```

**2. Copiar configuração:**
```bash
sudo cp /data/ch8-agent/website/apache-proxy.conf /etc/apache2/sites-available/ch8agent.conf
```

**3. Habilitar site:**
```bash
sudo a2ensite ch8agent
```

**4. Testar e aplicar:**
```bash
sudo apache2ctl configtest
sudo systemctl reload apache2
```

## 🌐 Passo 3: Configurar DNS no Cloudflare (2 minutos)

1. **Acesse:** https://dash.cloudflare.com/
2. **Selecione:** ch8ai.com.br
3. **Menu:** DNS → Records
4. **Add record:**

```
Type: A
Name: ch8agent
IPv4 address: 216.24.57.1
Proxy status: Proxied (🟠 laranja) - HTTPS automático!
TTL: Auto
```

5. **Save**

✅ **Pronto!** Aguarde 2-5 minutos para DNS propagar.

## ✅ Verificar

```bash
# 1. Container rodando
docker compose ps

# 2. Nginx/Apache rodando
sudo systemctl status nginx
# ou
sudo systemctl status apache2

# 3. DNS propagado
dig ch8agent.ch8ai.com.br

# 4. Site acessível
curl -I http://ch8agent.ch8ai.com.br
curl -I https://ch8agent.ch8ai.com.br
```

## 🔒 Passo 4: SSL/HTTPS (Opcional - se não usar Cloudflare Proxy)

Se você configurou DNS como "DNS only" (cinza) ao invés de "Proxied" (laranja):

### Usando Certbot (Let's Encrypt)

```bash
# Para Nginx
sudo certbot --nginx -d ch8agent.ch8ai.com.br

# Para Apache
sudo certbot --apache -d ch8agent.ch8ai.com.br

# Certbot configura HTTPS automaticamente!
```

Depois de gerar o certificado:
1. Edite o arquivo de configuração (nginx-proxy.conf ou apache-proxy.conf)
2. Descomente a seção HTTPS
3. Reload o servidor

## 📊 Estrutura Final

```
Internet
    ↓
Cloudflare (DNS + Proxy)
    ↓
216.24.57.1:443 (HTTPS)
    ↓
Nginx/Apache (Proxy Reverso)
    ↓
localhost:8080 (Container Docker)
    ↓
CH8 Agent Website
```

## 🔄 Fluxo de Requisição

```
https://ch8agent.ch8ai.com.br
    ↓
Cloudflare (SSL Termination)
    ↓
Nginx/Apache (Porta 443 → Proxy para 8080)
    ↓
Docker Container (Porta 8080)
    ↓
Website HTML/CSS/JS
```

## 📋 Checklist Completo

- [ ] Container Docker rodando na porta 8080
- [ ] `curl http://localhost:8080` funciona
- [ ] Nginx ou Apache configurado com proxy
- [ ] Configuração testada sem erros
- [ ] Servidor web recarregado
- [ ] DNS configurado no Cloudflare (A record)
- [ ] DNS propagado (dig mostra IP correto)
- [ ] `http://ch8agent.ch8ai.com.br` acessível
- [ ] `https://ch8agent.ch8ai.com.br` acessível (com HTTPS)
- [ ] Animações do site funcionando
- [ ] Mobile responsivo testado

## 🛠️ Comandos Úteis

### Gerenciar Container
```bash
cd /data/ch8-agent/website

# Ver logs
docker compose logs -f

# Restart
docker compose restart

# Parar
docker compose down

# Atualizar
git pull origin master
./deploy.sh
```

### Gerenciar Nginx
```bash
# Ver configuração
cat /etc/nginx/sites-available/ch8agent.conf

# Testar
sudo nginx -t

# Reload
sudo systemctl reload nginx

# Ver logs
sudo tail -f /var/log/nginx/ch8agent-access.log
sudo tail -f /var/log/nginx/ch8agent-error.log
```

### Gerenciar Apache
```bash
# Ver configuração
cat /etc/apache2/sites-available/ch8agent.conf

# Testar
sudo apache2ctl configtest

# Reload
sudo systemctl reload apache2

# Ver logs
sudo tail -f /var/log/apache2/ch8agent-access.log
sudo tail -f /var/log/apache2/ch8agent-error.log
```

## 🐛 Troubleshooting

### Erro 502 Bad Gateway

**Causa:** Nginx/Apache não consegue conectar ao container.

**Solução:**
```bash
# Verificar se container está rodando
docker compose ps

# Ver logs do container
docker compose logs

# Restart do container
docker compose restart

# Testar conexão local
curl http://localhost:8080
```

### Erro 503 Service Unavailable

**Causa:** Container parou ou não iniciou.

**Solução:**
```bash
# Verificar status
docker compose ps

# Ver logs
docker compose logs

# Restart
docker compose down
docker compose up -d --build
```

### DNS não resolve

**Solução:**
```bash
# Verificar configuração Cloudflare
dig ch8agent.ch8ai.com.br

# Aguardar propagação (até 5 minutos)
watch -n 5 'dig ch8agent.ch8ai.com.br'

# Testar com IP direto
curl http://216.24.57.1:8080
```

### Nginx/Apache não recarrega

**Solução:**
```bash
# Nginx
sudo nginx -t
sudo systemctl restart nginx

# Apache
sudo apache2ctl configtest
sudo systemctl restart apache2
```

### Porta 8080 já em uso

**Solução:**
```bash
# Ver o que está usando
sudo lsof -i :8080

# Usar outra porta (ex: 8081)
# Edite docker-compose.yml:
ports:
  - "8081:80"

# E atualize nginx-proxy.conf:
proxy_pass http://localhost:8081;

# Restart tudo
docker compose down
docker compose up -d
sudo systemctl reload nginx
```

## 🚀 Performance Tips

### Habilitar Cache no Nginx

Adicione ao nginx-proxy.conf:
```nginx
proxy_cache_path /var/cache/nginx/ch8agent levels=1:2 keys_zone=ch8agent_cache:10m max_size=100m inactive=60m;

server {
    # ... outras configs

    location / {
        proxy_cache ch8agent_cache;
        proxy_cache_valid 200 5m;
        proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;
        proxy_pass http://localhost:8080;
    }
}
```

### Habilitar Compressão

**Nginx:** (já habilitado por padrão)
```nginx
gzip on;
gzip_types text/plain text/css application/json application/javascript image/svg+xml;
```

**Apache:**
```bash
sudo a2enmod deflate
```

### HTTP/2

**Nginx:** (se tiver SSL)
```nginx
listen 443 ssl http2;
```

**Apache:**
```bash
sudo a2enmod http2
# Adicione ao VirtualHost:
Protocols h2 http/1.1
```

## 📊 Monitoramento

### Ver Tráfego em Tempo Real

**Nginx:**
```bash
sudo tail -f /var/log/nginx/ch8agent-access.log
```

**Apache:**
```bash
sudo tail -f /var/log/apache2/ch8agent-access.log
```

### Estatísticas

```bash
# Requests por hora
sudo cat /var/log/nginx/ch8agent-access.log | awk '{print $4}' | cut -d: -f1-2 | sort | uniq -c

# Top IPs
sudo cat /var/log/nginx/ch8agent-access.log | awk '{print $1}' | sort | uniq -c | sort -rn | head
```

## 🎯 Resumo Visual

```
┌─────────────────────────────────────┐
│  Cloudflare DNS                     │
│  ch8agent.ch8ai.com.br → 216.24.57.1│
└──────────────┬──────────────────────┘
               │ HTTPS
               ▼
┌─────────────────────────────────────┐
│  Seu Servidor (216.24.57.1)         │
│                                     │
│  ┌─────────────────────┐            │
│  │ Nginx/Apache :443   │            │
│  │ Proxy Reverso       │            │
│  └─────────┬───────────┘            │
│            │ localhost:8080         │
│            ▼                        │
│  ┌─────────────────────┐            │
│  │ Docker Container    │            │
│  │ CH8 Agent Website   │            │
│  └─────────────────────┘            │
│                                     │
│  ┌─────────────────────┐            │
│  │ Outros Sites        │            │
│  │ www.ch8ai.com.br    │            │
│  └─────────────────────┘            │
└─────────────────────────────────────┘
```

---

**Tempo total:** 7 minutos
**Resultado:** Website no ar em ch8agent.ch8ai.com.br sem conflitar com sites existentes! 🎉
