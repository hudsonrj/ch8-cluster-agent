# Deploy no Cloudflare Pages - ch8agent.ch8ai.com.br

Guia completo para colocar o site no ar em **ch8agent.ch8ai.com.br** usando Cloudflare Pages.

## 🚀 Passo 1: Deploy no Cloudflare Pages

### 1.1 Acessar Cloudflare Pages

1. Acesse: https://dash.cloudflare.com/
2. Faça login com sua conta
3. No menu lateral, clique em **Pages**
4. Clique em **Create a project**

### 1.2 Conectar GitHub Repository

1. Clique em **Connect to Git**
2. Autorize o Cloudflare a acessar seu GitHub
3. Selecione o repositório: **hudsonrj/ch8-cluster-agent**
4. Clique em **Begin setup**

### 1.3 Configurar Build Settings

Configure os seguintes campos:

```
Project name: ch8agent
Production branch: master
Build command: (deixe vazio)
Build output directory: website
Root directory: /
```

**IMPORTANTE:** O diretório de saída é `website` porque os arquivos estão em `/website` no repositório.

### 1.4 Deploy

1. Clique em **Save and Deploy**
2. Aguarde 1-2 minutos (primeiro deploy demora um pouco)
3. Você receberá uma URL temporária tipo: `ch8agent.pages.dev`

✅ **Site já está no ar!** (mas ainda na URL temporária)

## 🌐 Passo 2: Configurar DNS no Cloudflare

Agora vamos fazer o site responder em **ch8agent.ch8ai.com.br**

### 2.1 Adicionar Custom Domain no Cloudflare Pages

1. No Cloudflare Pages, clique no projeto **ch8agent**
2. Vá para aba **Custom domains**
3. Clique em **Set up a custom domain**
4. Digite: `ch8agent.ch8ai.com.br`
5. Clique em **Continue**

### 2.2 Cloudflare vai criar automaticamente o registro DNS

O Cloudflare detectará que você já gerencia `ch8ai.com.br` e perguntará:

- **"Activate domain"** → Clique **Activate domain**

Ele criará automaticamente um registro CNAME no DNS.

### 2.3 Verificar DNS (Alternativa Manual)

Se precisar configurar manualmente, vá em **DNS** → **Records**:

1. Clique em **Add record**
2. Configure:
   ```
   Type: CNAME
   Name: ch8agent
   Target: ch8agent.pages.dev
   Proxy status: Proxied (laranja, não cinza)
   TTL: Auto
   ```
3. Clique em **Save**

## ✅ Configuração Final

### Verificar Status

1. **DNS:** Cloudflare Pages → Custom domains
   - Deve mostrar: ✅ Active (em verde)

2. **SSL:** Automático
   - Cloudflare já gera certificado SSL
   - HTTPS será forçado automaticamente

3. **Teste:** Abra em até 5 minutos
   ```
   https://ch8agent.ch8ai.com.br
   ```

## 🎨 Configurações Adicionais (Opcional)

### 1. Redirecionar www para não-www

No Cloudflare Pages → Custom domains:

1. Adicione também: `www.ch8agent.ch8ai.com.br`
2. Cloudflare redirecionará automaticamente para `ch8agent.ch8ai.com.br`

### 2. Configurar Cache Rules

Dashboard Cloudflare → **Caching** → **Configuration**:

```
Browser Cache TTL: 1 year
```

### 3. Habilitar Auto Minify

Dashboard → **Speed** → **Optimization**:

- ✅ JavaScript
- ✅ CSS
- ✅ HTML

### 4. Habilitar HTTP/3

Dashboard → **Network**:

- ✅ HTTP/3 (with QUIC)
- ✅ 0-RTT Connection Resumption

### 5. Page Rules (Opcional)

Dashboard → **Rules** → **Page Rules**:

Criar regra para cache de assets:
```
URL: ch8agent.ch8ai.com.br/*.css
      ch8agent.ch8ai.com.br/*.js
      ch8agent.ch8ai.com.br/*.svg

Settings:
- Cache Level: Cache Everything
- Edge Cache TTL: 1 month
```

## 🔄 Deploy Automático (Já Configurado!)

Agora, sempre que você fizer push no GitHub:

```bash
git add .
git commit -m "update website"
git push origin master
```

O Cloudflare Pages vai automaticamente:
1. Detectar o push
2. Fazer rebuild
3. Atualizar o site em ~1 minuto

## 📊 Monitoramento

### Analytics Gratuito do Cloudflare

1. Dashboard → **Analytics** → **Web Analytics**
2. Copie o código JavaScript
3. Adicione no `website/index.html` antes de `</head>`:

```html
<!-- Cloudflare Web Analytics -->
<script defer src='https://static.cloudflareinsights.com/beacon.min.js'
        data-cf-beacon='{"token": "SEU_TOKEN_AQUI"}'></script>
```

### Ver Logs de Deploy

Cloudflare Pages → Deployments:
- Ver histórico de builds
- Ver logs de erro
- Fazer rollback se necessário

## 🚀 Performance

Com Cloudflare Pages você tem automaticamente:

✅ **CDN Global:** 200+ data centers
✅ **SSL Gratuito:** Certificado automático
✅ **HTTP/3:** Protocolo mais rápido
✅ **Brotli Compression:** Arquivos menores
✅ **Cache Inteligente:** Assets em cache
✅ **DDoS Protection:** Proteção automática
✅ **Zero Downtime:** Deploys sem parar o site

## 🔍 Troubleshooting

### Site não carrega

1. **Verificar DNS propagação:**
   ```bash
   dig ch8agent.ch8ai.com.br
   nslookup ch8agent.ch8ai.com.br
   ```

2. **Verificar SSL:**
   ```bash
   curl -I https://ch8agent.ch8ai.com.br
   ```

3. **Ver logs:**
   - Cloudflare Pages → Deployments → Ver último deploy

### Erro 522 (Connection Timeout)

- Aguarde 5 minutos (DNS propagando)
- Verifique se o deploy foi bem sucedido
- Cloudflare Pages → Deployments → Status deve ser "Success"

### CSS/JS não carrega (404)

- Verifique se `Build output directory` está como `website`
- Refaça deploy: Cloudflare Pages → Deployments → Retry deployment

### Mudanças não aparecem

- **Cache do browser:** Ctrl+Shift+R (hard refresh)
- **Cache do Cloudflare:**
  - Dashboard → Caching → Purge Everything

## 🎯 Checklist Rápido

Marque conforme vai fazendo:

- [ ] Cloudflare Pages criado e conectado ao GitHub
- [ ] Build configurado com `website` como output
- [ ] Primeiro deploy concluído com sucesso
- [ ] Custom domain `ch8agent.ch8ai.com.br` adicionado
- [ ] DNS ativo (✅ Active)
- [ ] SSL ativo (🔒 HTTPS funcionando)
- [ ] Site abre em https://ch8agent.ch8ai.com.br
- [ ] Animações funcionando
- [ ] Particles.js carregando
- [ ] Tabs de instalação funcionando
- [ ] Botões copy-to-clipboard funcionando
- [ ] Mobile responsivo testado

## 📱 Testar em Múltiplos Devices

```bash
# Ver como aparece em diferentes resoluções
https://www.responsinator.com/?url=ch8agent.ch8ai.com.br

# Google Mobile-Friendly Test
https://search.google.com/test/mobile-friendly?url=ch8agent.ch8ai.com.br

# PageSpeed Insights
https://pagespeed.web.dev/analysis?url=ch8agent.ch8ai.com.br
```

## 🎉 Pronto!

Seu site está no ar em:
```
https://ch8agent.ch8ai.com.br
```

Com:
- ⚡ CDN global (200+ locais)
- 🔒 SSL automático
- 🚀 HTTP/3 habilitado
- 📊 Analytics disponível
- 🔄 Deploy automático no push
- 🛡️ DDoS protection
- 💾 Cache otimizado
- 🌍 99.99% uptime

---

**Tempo total:** 5-10 minutos
**Custo:** 100% gratuito
**Manutenção:** Zero (tudo automático)
