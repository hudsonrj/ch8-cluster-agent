# SSL Certificate Setup - Let's Encrypt

Certificado SSL válido configurado para **ch8agent.ch8ai.com.br**

## ✅ Status Atual

```
Emissor: Let's Encrypt (E7)
Domínio: ch8agent.ch8ai.com.br
Válido de: 22 Abril 2026
Válido até: 21 Julho 2026 (90 dias)
Status: ✅ ATIVO E VÁLIDO
```

## 🔒 Certificados Instalados

```
Localização Let's Encrypt:
/etc/letsencrypt/live/ch8agent.ch8ai.com.br/fullchain.pem
/etc/letsencrypt/live/ch8agent.ch8ai.com.br/privkey.pem

Copiados para Nginx:
/data/govgpt/nginx/ssl/ch8agent-cert.pem
/data/govgpt/nginx/ssl/ch8agent-key.pem
```

## 🔄 Renovação Automática

O Certbot configurou automaticamente a renovação via systemd timer.

### Verificar Status da Renovação

```bash
# Ver status do timer
sudo systemctl status certbot.timer

# Testar renovação (dry-run)
sudo certbot renew --dry-run

# Ver quando os certificados expiram
sudo certbot certificates
```

### Renovação Manual (se necessário)

```bash
# Parar Nginx temporariamente
docker stop govgpt-nginx

# Renovar certificado
sudo certbot renew

# Copiar novos certificados
sudo cp /etc/letsencrypt/live/ch8agent.ch8ai.com.br/fullchain.pem /data/govgpt/nginx/ssl/ch8agent-cert.pem
sudo cp /etc/letsencrypt/live/ch8agent.ch8ai.com.br/privkey.pem /data/govgpt/nginx/ssl/ch8agent-key.pem

# Restart Nginx
docker start govgpt-nginx
docker exec govgpt-nginx nginx -s reload
```

## 🤖 Script de Renovação Automática

Criar script para renovação e reload automático:

**`/usr/local/bin/renew-ch8agent-cert.sh`:**

```bash
#!/bin/bash
set -e

echo "🔄 Renovando certificado SSL para ch8agent.ch8ai.com.br..."

# Para Nginx
docker stop govgpt-nginx

# Renova certificado
certbot renew --quiet

# Copia certificados atualizados
cp /etc/letsencrypt/live/ch8agent.ch8ai.com.br/fullchain.pem /data/govgpt/nginx/ssl/ch8agent-cert.pem
cp /etc/letsencrypt/live/ch8agent.ch8ai.com.br/privkey.pem /data/govgpt/nginx/ssl/ch8agent-key.pem

# Reinicia Nginx
docker start govgpt-nginx
sleep 5
docker exec govgpt-nginx nginx -s reload

echo "✅ Certificado renovado e Nginx recarregado!"
```

Tornar executável:
```bash
sudo chmod +x /usr/local/bin/renew-ch8agent-cert.sh
```

### Adicionar ao Cron (Mensal)

```bash
# Editar crontab
sudo crontab -e

# Adicionar linha (roda 1º dia do mês às 3am)
0 3 1 * * /usr/local/bin/renew-ch8agent-cert.sh >> /var/log/certbot-renewal.log 2>&1
```

## 🛡️ Security Headers Configurados

```nginx
X-Frame-Options: SAMEORIGIN
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
Referrer-Policy: no-referrer-when-downgrade
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

## 🔍 Verificar Certificado

### Via Navegador
Acesse: https://ch8agent.ch8ai.com.br
- Clique no cadeado
- Ver informações do certificado
- Deve mostrar: Let's Encrypt

### Via Linha de Comando

```bash
# Testar conexão SSL
curl -I https://ch8agent.ch8ai.com.br

# Ver detalhes do certificado
echo | openssl s_client -connect ch8agent.ch8ai.com.br:443 -servername ch8agent.ch8ai.com.br 2>/dev/null | openssl x509 -noout -text

# Verificar data de expiração
echo | openssl s_client -connect ch8agent.ch8ai.com.br:443 -servername ch8agent.ch8ai.com.br 2>/dev/null | openssl x509 -noout -dates
```

### Via SSL Labs

Teste completo de segurança:
https://www.ssllabs.com/ssltest/analyze.html?d=ch8agent.ch8ai.com.br

## 📊 SSL Configuration

### Protocolos Suportados
- TLSv1.2 ✅
- TLSv1.3 ✅

### Ciphers
- HIGH:!aNULL:!MD5

### Session Cache
- Shared: 10MB
- Timeout: 10 minutos

### HTTP/2
- Habilitado ✅

## 🔧 Troubleshooting

### Certificado não carrega

```bash
# Verificar se arquivos existem
ls -la /data/govgpt/nginx/ssl/ch8agent-*

# Verificar permissões
# cert.pem deve ser 644
# key.pem deve ser 600

# Recarregar Nginx
docker exec govgpt-nginx nginx -s reload
```

### Erro de certificado expirado

```bash
# Renovar manualmente
sudo certbot renew --force-renewal

# Copiar novos certificados
sudo cp /etc/letsencrypt/live/ch8agent.ch8ai.com.br/fullchain.pem /data/govgpt/nginx/ssl/ch8agent-cert.pem
sudo cp /etc/letsencrypt/live/ch8agent.ch8ai.com.br/privkey.pem /data/govgpt/nginx/ssl/ch8agent-key.pem

# Reload
docker exec govgpt-nginx nginx -s reload
```

### Browser ainda mostra aviso

- Limpar cache do navegador (Ctrl+Shift+Delete)
- Testar em navegação anônima
- Verificar se DNS está correto: `dig ch8agent.ch8ai.com.br`
- Aguardar 5 minutos para propagação de cache

### Verificar logs

```bash
# Logs do Certbot
sudo tail -f /var/log/letsencrypt/letsencrypt.log

# Logs do Nginx
docker exec govgpt-nginx tail -f /var/log/nginx/ch8agent-error.log
docker exec govgpt-nginx tail -f /var/log/nginx/ch8agent-access.log
```

## 📅 Cronograma de Manutenção

- **Automático**: Certbot timer renova a cada 12 horas (tenta, só renova se < 30 dias)
- **Manual (recomendado)**: Verificar mensalmente
- **Crítico**: Renovar antes de 85 dias (5 dias antes do vencimento)

## 🎯 Checklist

- [x] Certbot instalado
- [x] Certificado Let's Encrypt gerado
- [x] Certificados copiados para Nginx
- [x] Configuração Nginx atualizada
- [x] Nginx recarregado
- [x] HTTPS funcionando
- [x] Certificado válido verificado
- [x] HTTP → HTTPS redirect ativo
- [x] Security headers configurados
- [x] HTTP/2 habilitado
- [x] Renovação automática configurada
- [ ] Script de renovação criado (opcional)
- [ ] Cron job configurado (opcional)
- [ ] Teste SSL Labs realizado (opcional)

## 🔗 Links Úteis

- Let's Encrypt: https://letsencrypt.org/
- Certbot Documentation: https://certbot.eff.org/
- SSL Labs Test: https://www.ssllabs.com/ssltest/
- Mozilla SSL Configuration: https://ssl-config.mozilla.org/

---

**Status**: ✅ **SSL ATIVO E VÁLIDO** - Conexão 100% segura! 🔒
