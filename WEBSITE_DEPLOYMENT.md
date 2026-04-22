# Website Deployment Guide

Complete guide to deploy the CH8 Agent landing page.

## Quick Deploy to GitHub Pages

The easiest way to make your website live:

### 1. Push to GitHub

```bash
git push origin master
```

### 2. Enable GitHub Pages

1. Go to your repository: `https://github.com/hudsonrj/ch8-cluster-agent`
2. Click **Settings** → **Pages** (in the left sidebar)
3. Under **Source**:
   - Branch: `master`
   - Folder: `/website`
   - Click **Save**

### 3. Access Your Site

After 1-2 minutes, your site will be live at:
```
https://hudsonrj.github.io/ch8-cluster-agent/
```

## Alternative Deployment Options

### Option 1: Netlify (One-Click Deploy)

[![Deploy to Netlify](https://www.netlify.com/img/deploy/button.svg)](https://app.netlify.com/start)

1. Click the button above
2. Connect your GitHub account
3. Select the `ch8-cluster-agent` repository
4. Base directory: `website`
5. Deploy!

**Or use Netlify CLI:**

```bash
# Install Netlify CLI
npm install -g netlify-cli

# Deploy
cd website/
netlify deploy --prod

# Follow the prompts
```

### Option 2: Vercel

```bash
# Install Vercel CLI
npm install -g vercel

# Deploy
cd website/
vercel --prod
```

Or use the Vercel GitHub integration:
1. Go to [vercel.com](https://vercel.com)
2. Import your GitHub repository
3. Set root directory to `website`
4. Deploy!

### Option 3: Cloudflare Pages

1. Go to [Cloudflare Pages](https://pages.cloudflare.com/)
2. Connect your GitHub repository
3. Build settings:
   - Build command: (leave empty)
   - Build output directory: `website`
4. Deploy!

### Option 4: Custom Server

#### Nginx

Create `/etc/nginx/sites-available/ch8agent`:

```nginx
server {
    listen 80;
    server_name ch8agent.example.com;

    root /var/www/ch8-agent/website;
    index index.html;

    # Enable gzip
    gzip on;
    gzip_comp_level 6;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript image/svg+xml;

    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache static assets
    location ~* \.(css|js|jpg|jpeg|png|gif|svg|ico|woff|woff2)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
}
```

Enable and restart:
```bash
sudo ln -s /etc/nginx/sites-available/ch8agent /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

#### Apache

Create `/etc/apache2/sites-available/ch8agent.conf`:

```apache
<VirtualHost *:80>
    ServerName ch8agent.example.com
    DocumentRoot /var/www/ch8-agent/website

    <Directory /var/www/ch8-agent/website>
        Options -Indexes +FollowSymLinks
        AllowOverride All
        Require all granted
    </Directory>

    # Enable compression
    <IfModule mod_deflate.c>
        AddOutputFilterByType DEFLATE text/html text/plain text/xml text/css application/javascript image/svg+xml
    </IfModule>

    # Cache static assets
    <IfModule mod_expires.c>
        ExpiresActive On
        ExpiresByType text/css "access plus 1 year"
        ExpiresByType application/javascript "access plus 1 year"
        ExpiresByType image/svg+xml "access plus 1 year"
        ExpiresByType image/png "access plus 1 year"
    </IfModule>

    ErrorLog ${APACHE_LOG_DIR}/ch8agent_error.log
    CustomLog ${APACHE_LOG_DIR}/ch8agent_access.log combined
</VirtualHost>
```

Enable and restart:
```bash
sudo a2ensite ch8agent
sudo a2enmod deflate expires headers
sudo apache2ctl configtest
sudo systemctl reload apache2
```

#### Docker

Create `website/Dockerfile`:

```dockerfile
FROM nginx:alpine

COPY . /usr/share/nginx/html

# Custom nginx config
RUN echo 'server { \
    listen 80; \
    root /usr/share/nginx/html; \
    index index.html; \
    gzip on; \
    gzip_types text/css application/javascript image/svg+xml; \
    location / { try_files $uri $uri/ /index.html; } \
    location ~* \.(css|js|svg|png|jpg)$ { expires 1y; add_header Cache-Control "public, immutable"; } \
}' > /etc/nginx/conf.d/default.conf

EXPOSE 80
```

Build and run:
```bash
cd website/
docker build -t ch8agent-website .
docker run -d -p 80:80 ch8agent-website
```

## Custom Domain Setup

### For GitHub Pages

1. Create `website/CNAME` file:
   ```
   ch8agent.yourdomain.com
   ```

2. Add to your DNS:
   ```
   CNAME   ch8agent   hudsonrj.github.io
   ```

3. In GitHub Settings → Pages:
   - Enter your custom domain
   - Check "Enforce HTTPS"

### For Netlify/Vercel

Add domain in dashboard:
1. Go to Domain settings
2. Add custom domain
3. Follow DNS instructions
4. SSL is automatic

## Testing Locally

Before deploying, test locally:

```bash
# Method 1: Python
cd website/
python3 -m http.server 8000
# Visit http://localhost:8000

# Method 2: Node.js
npx http-server website/ -p 8000

# Method 3: PHP
php -S localhost:8000 -t website/
```

## Performance Optimization

### 1. Enable CDN (if using custom server)

Use Cloudflare or similar:
1. Add your domain to Cloudflare
2. Change nameservers
3. Enable "Always Online"
4. Set cache rules

### 2. Image Optimization (for future images)

```bash
# Install tools
npm install -g imagemin-cli imagemin-webp

# Optimize PNG/JPG
imagemin website/*.{jpg,png} --out-dir=website/optimized

# Convert to WebP
imagemin website/*.{jpg,png} --plugin=webp --out-dir=website/webp
```

### 3. CSS/JS Minification (optional)

```bash
# Install tools
npm install -g clean-css-cli uglify-js

# Minify CSS
cleancss -o website/styles.min.css website/styles.css

# Minify JS
uglifyjs website/script.js -o website/script.min.js

# Update index.html to use .min versions
```

### 4. Enable HTTP/2

For Nginx:
```nginx
listen 443 ssl http2;
```

For Apache:
```bash
sudo a2enmod http2
# Add to VirtualHost:
Protocols h2 http/1.1
```

## SSL/HTTPS Setup

### Free SSL with Let's Encrypt

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# For Nginx
sudo certbot --nginx -d ch8agent.example.com

# For Apache
sudo apt install python3-certbot-apache
sudo certbot --apache -d ch8agent.example.com

# Auto-renewal (already set up by certbot)
sudo certbot renew --dry-run
```

## Monitoring

### Basic Analytics (Google Analytics)

Add to `index.html` before `</head>`:

```html
<!-- Google Analytics -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-XXXXXXXXXX');
</script>
```

### Privacy-Friendly Alternative (Plausible)

```html
<script defer data-domain="ch8agent.example.com" src="https://plausible.io/js/script.js"></script>
```

### Uptime Monitoring

Free services:
- [UptimeRobot](https://uptimerobot.com/) - 50 monitors free
- [StatusCake](https://www.statuscake.com/) - 10 monitors free
- [Freshping](https://www.freshworks.com/website-monitoring/) - 50 checks free

## SEO Optimization

### 1. Add sitemap.xml

Create `website/sitemap.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://hudsonrj.github.io/ch8-cluster-agent/</loc>
    <lastmod>2024-04-22</lastmod>
    <priority>1.0</priority>
  </url>
</urlset>
```

### 2. Add robots.txt

Create `website/robots.txt`:

```
User-agent: *
Allow: /

Sitemap: https://hudsonrj.github.io/ch8-cluster-agent/sitemap.xml
```

### 3. Improve Meta Tags

Already added in `index.html`, but verify:
- Title is descriptive and under 60 chars
- Description is compelling and under 160 chars
- Open Graph tags for social sharing
- Twitter Card tags

### 4. Submit to Search Engines

- [Google Search Console](https://search.google.com/search-console)
- [Bing Webmaster Tools](https://www.bing.com/webmasters)

## Troubleshooting

### Site Not Loading

1. **Check DNS propagation:**
   ```bash
   dig ch8agent.example.com
   nslookup ch8agent.example.com
   ```

2. **Check web server status:**
   ```bash
   sudo systemctl status nginx
   sudo systemctl status apache2
   ```

3. **Check logs:**
   ```bash
   # Nginx
   sudo tail -f /var/log/nginx/error.log

   # Apache
   sudo tail -f /var/log/apache2/error.log
   ```

### Assets Not Loading (404)

1. **Check file paths** are correct in `index.html`
2. **Check file permissions:**
   ```bash
   sudo chmod -R 755 /var/www/ch8-agent/website
   ```

3. **Check base URL** in your HTML matches deployment path

### Animations Not Working

1. **Check browser console** for JavaScript errors
2. **Verify CDN links** are accessible:
   - particles.js
   - AOS (Animate on Scroll)
   - Font Awesome
3. **Clear browser cache** (Ctrl+Shift+R)

### Slow Loading

1. **Enable compression** (gzip/brotli)
2. **Use CDN** for static assets
3. **Enable browser caching**
4. **Minimize external requests**
5. **Use async/defer** for scripts

## Continuous Deployment

### GitHub Actions

Create `.github/workflows/deploy-website.yml`:

```yaml
name: Deploy Website

on:
  push:
    branches: [ master ]
    paths:
      - 'website/**'

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3

    # Option 1: Deploy to GitHub Pages
    - name: Deploy to GitHub Pages
      uses: peaceiris/actions-gh-pages@v3
      with:
        github_token: ${{ secrets.GITHUB_TOKEN }}
        publish_dir: ./website

    # Option 2: Deploy to Netlify
    - name: Deploy to Netlify
      uses: nwtgck/actions-netlify@v2
      with:
        publish-dir: './website'
        production-deploy: true
      env:
        NETLIFY_AUTH_TOKEN: ${{ secrets.NETLIFY_AUTH_TOKEN }}
        NETLIFY_SITE_ID: ${{ secrets.NETLIFY_SITE_ID }}
```

## Post-Deployment Checklist

- [ ] Site loads correctly at production URL
- [ ] All links work (navigation, GitHub, etc.)
- [ ] Animations play smoothly
- [ ] Copy-to-clipboard buttons work
- [ ] Tabs switch properly
- [ ] Mobile responsive design works
- [ ] Particles animation loads
- [ ] All code blocks are visible
- [ ] SSL/HTTPS enabled
- [ ] Custom domain configured (if applicable)
- [ ] Analytics tracking works (if added)
- [ ] Sitemap submitted to search engines
- [ ] Tested in Chrome, Firefox, Safari
- [ ] Page load time < 3 seconds
- [ ] Lighthouse score > 90

## Useful Commands

```bash
# Check if site is live
curl -I https://hudsonrj.github.io/ch8-cluster-agent/

# Test performance
npx lighthouse https://hudsonrj.github.io/ch8-cluster-agent/ --view

# Validate HTML
npx html-validate website/index.html

# Check broken links
npx linkinator https://hudsonrj.github.io/ch8-cluster-agent/

# Analyze bundle size
npx bundlephobia website/
```

## Support

For deployment issues:
- GitHub Pages: [Pages Documentation](https://docs.github.com/en/pages)
- Netlify: [Netlify Docs](https://docs.netlify.com/)
- Vercel: [Vercel Docs](https://vercel.com/docs)

For website bugs:
- Create issue: https://github.com/hudsonrj/ch8-cluster-agent/issues
- Tag: `website`

---

**Your CH8 Agent landing page is ready to showcase democratic AI to the world!**
