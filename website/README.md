# CH8 Agent Landing Page

Modern, highly technological landing page for CH8 Agent - Democratic Distributed AI.

## Features

- Animated particle background using particles.js
- Smooth scroll animations with AOS
- Interactive SVG diagrams showing distributed architecture
- Typing effect on hero title
- Multi-platform installation tabs
- Responsive design for all screen sizes
- Copy-to-clipboard functionality for code blocks
- Animated statistics counters
- Gradient effects and modern UI

## Technologies

- HTML5
- CSS3 with custom animations and gradients
- JavaScript with:
  - [particles.js](https://particles.js.org/) - Interactive particle background
  - [AOS](https://michalsnik.github.io/aos/) - Animate on Scroll library
  - Custom SVG animations
  - Tab navigation
  - Smooth scrolling

## Local Testing

### Option 1: Python HTTP Server
```bash
cd website/
python3 -m http.server 8000
# Open http://localhost:8000
```

### Option 2: Node.js HTTP Server
```bash
cd website/
npx http-server -p 8000
# Open http://localhost:8000
```

### Option 3: PHP Built-in Server
```bash
cd website/
php -S localhost:8000
# Open http://localhost:8000
```

## Deployment

### GitHub Pages (Recommended)

1. **Enable GitHub Pages:**
   ```bash
   # From project root
   git checkout master
   # Pages will serve from /website directory
   ```

2. **Configure on GitHub:**
   - Go to repository Settings → Pages
   - Source: Deploy from a branch
   - Branch: `master` / `website` folder
   - Save

3. **Access:** `https://hudsonrj.github.io/ch8-cluster-agent/`

### Netlify

1. **Deploy:**
   ```bash
   # Install Netlify CLI
   npm install -g netlify-cli

   # Deploy
   cd website/
   netlify deploy --prod
   ```

2. **Or use Netlify Drop:** Drag the `website/` folder to [Netlify Drop](https://app.netlify.com/drop)

### Vercel

```bash
# Install Vercel CLI
npm install -g vercel

# Deploy
cd website/
vercel --prod
```

### Custom Server (Nginx)

```nginx
server {
    listen 80;
    server_name ch8agent.example.com;

    root /var/www/ch8-agent/website;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    # Enable gzip compression
    gzip on;
    gzip_types text/css application/javascript image/svg+xml;

    # Cache static assets
    location ~* \.(css|js|jpg|jpeg|png|gif|svg|ico)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

### Custom Server (Apache)

Create `.htaccess`:
```apache
# Enable rewrite engine
RewriteEngine On

# Redirect to HTTPS
RewriteCond %{HTTPS} off
RewriteRule ^(.*)$ https://%{HTTP_HOST}%{REQUEST_URI} [L,R=301]

# Enable compression
<IfModule mod_deflate.c>
    AddOutputFilterByType DEFLATE text/html text/css application/javascript image/svg+xml
</IfModule>

# Cache static assets
<IfModule mod_expires.c>
    ExpiresActive On
    ExpiresByType text/css "access plus 1 year"
    ExpiresByType application/javascript "access plus 1 year"
    ExpiresByType image/svg+xml "access plus 1 year"
    ExpiresByType image/png "access plus 1 year"
    ExpiresByType image/jpeg "access plus 1 year"
</IfModule>
```

## Customization

### Colors
Edit CSS variables in `styles.css`:
```css
:root {
    --primary: #00f2ff;     /* Cyan */
    --secondary: #7000ff;   /* Purple */
    --accent: #ff00ff;      /* Magenta */
    --bg-dark: #0a0e1a;     /* Dark blue */
    --bg-darker: #050810;   /* Darker blue */
}
```

### Content
- **Hero stats:** Edit in `index.html` lines 50-70
- **Features:** Edit in `index.html` lines 200-350
- **Installation commands:** Edit in `index.html` lines 500-700
- **Repository URL:** Update all GitHub links to match your fork

### Animations
- **Particle density:** Edit `script.js` line 5 (`value: 80`)
- **Animation speed:** Edit `script.js` line 34 (`speed: 2`)
- **Scroll animation duration:** Edit `script.js` line 61 (`duration: 1000`)

## Structure

```
website/
├── index.html          # Main HTML structure
├── styles.css          # All styling and animations
├── script.js           # Interactive functionality
└── README.md           # This file
```

## External Dependencies (CDN)

All dependencies are loaded via CDN, no installation needed:
- Google Fonts (Inter, Fira Code)
- Font Awesome 6.0.0 (icons)
- particles.js 2.0.0 (background animation)
- AOS 2.3.4 (scroll animations)

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Opera 76+

## Performance

- Lightweight: ~50KB total (HTML + CSS + JS)
- External assets: ~300KB (fonts, libraries)
- Fast loading with CDN caching
- Optimized animations using CSS transforms
- Lazy loading for images (ready for future additions)

## SEO

To improve SEO, add to `<head>` in `index.html`:

```html
<!-- Meta tags -->
<meta name="description" content="CH8 Agent - Democratic Distributed AI. Run small LLMs on any device, from Raspberry Pi to Android, working together for better results.">
<meta name="keywords" content="distributed AI, small LLMs, Raspberry Pi, Android, Ollama, local LLM, democratic AI">
<meta name="author" content="CH8 Agent Team">

<!-- Open Graph -->
<meta property="og:title" content="CH8 Agent - Democratic Distributed AI">
<meta property="og:description" content="Run small LLMs on any device working together">
<meta property="og:image" content="https://yoursite.com/preview.png">
<meta property="og:url" content="https://yoursite.com">

<!-- Twitter Card -->
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="CH8 Agent - Democratic Distributed AI">
<meta name="twitter:description" content="Run small LLMs on any device working together">
<meta name="twitter:image" content="https://yoursite.com/preview.png">
```

## Analytics (Optional)

Add Google Analytics:
```html
<!-- Before closing </head> -->
<script async src="https://www.googletagmanager.com/gtag/js?id=GA_MEASUREMENT_ID"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'GA_MEASUREMENT_ID');
</script>
```

## License

Same as main project - MIT License

## Support

For issues or questions about the website:
- GitHub Issues: https://github.com/hudsonrj/ch8-cluster-agent/issues
- Website specific tag: `website`
