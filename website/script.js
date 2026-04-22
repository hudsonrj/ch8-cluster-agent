// Particles
particlesJS('particles-js', {
    particles: {
        number: { value: 35, density: { enable: true, value_area: 1800 } },
        color: { value: '#0070f3' },
        shape: { type: 'circle' },
        opacity: { value: 0.2, random: true },
        size: { value: 2, random: true },
        line_linked: {
            enable: true,
            distance: 160,
            color: '#0070f3',
            opacity: 0.06,
            width: 1
        },
        move: { enable: true, speed: 0.8, direction: 'none', random: true, out_mode: 'out' }
    },
    interactivity: {
        detect_on: 'canvas',
        events: { onhover: { enable: false }, onclick: { enable: false }, resize: true }
    },
    retina_detect: true
});

// AOS
AOS.init({ duration: 550, once: true, offset: 40, easing: 'ease-out' });

// Tabs
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const tab = btn.dataset.tab;
        const container = btn.closest('.install-wrapper') || document;

        container.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        container.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

        btn.classList.add('active');
        const pane = document.getElementById(tab);
        if (pane) pane.classList.add('active');
    });
});

// Copy buttons
document.querySelectorAll('.copy-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const block = btn.closest('.code-block');
        const code = block.querySelector('code');
        if (!code) return;

        navigator.clipboard.writeText(code.textContent.trim()).then(() => {
            const orig = btn.innerHTML;
            btn.innerHTML = '<i class="fas fa-check"></i>';
            btn.style.color = '#10b981';
            setTimeout(() => {
                btn.innerHTML = orig;
                btn.style.color = '';
            }, 2000);
        });
    });
});

// Smooth scroll
document.querySelectorAll('a[href^="#"]').forEach(a => {
    a.addEventListener('click', e => {
        e.preventDefault();
        const target = document.querySelector(a.getAttribute('href'));
        if (target) {
            window.scrollTo({ top: target.offsetTop - 72, behavior: 'smooth' });
        }
    });
});

// Navbar scroll
const navbar = document.querySelector('.navbar');
window.addEventListener('scroll', () => {
    navbar.style.boxShadow = window.scrollY > 20
        ? '0 1px 0 rgba(255,255,255,0.04)'
        : 'none';
});

// Mobile menu
const mobileBtn = document.querySelector('.mobile-menu-btn');
const navLinks  = document.querySelector('.nav-links');
if (mobileBtn && navLinks) {
    mobileBtn.addEventListener('click', () => {
        const open = navLinks.classList.toggle('mobile-open');
        mobileBtn.innerHTML = open
            ? '<i class="fas fa-times"></i>'
            : '<i class="fas fa-bars"></i>';
        if (open) {
            navLinks.style.cssText = `
                display: flex;
                flex-direction: column;
                position: fixed;
                top: 56px; left: 0; right: 0;
                background: rgba(5,5,5,0.97);
                backdrop-filter: blur(20px);
                border-bottom: 1px solid rgba(255,255,255,0.08);
                padding: 1.5rem;
                gap: 1rem;
                z-index: 99;
            `;
        } else {
            navLinks.style.cssText = '';
        }
    });
}

// Stat counter animation
function animateCount(el) {
    const text = el.textContent;
    const match = text.match(/\d+/);
    if (!match) return;
    const end = parseInt(match[0]);
    const prefix = text.slice(0, text.indexOf(match[0]));
    const suffix = text.slice(text.indexOf(match[0]) + match[0].length);
    const duration = 1200;
    let start = null;

    function step(ts) {
        if (!start) start = ts;
        const p = Math.min((ts - start) / duration, 1);
        const val = Math.floor(p * end);
        el.textContent = prefix + val + suffix;
        if (p < 1) requestAnimationFrame(step);
        else el.textContent = text;
    }
    requestAnimationFrame(step);
}

const io = new IntersectionObserver(entries => {
    entries.forEach(e => {
        if (e.isIntersecting) {
            e.target.querySelectorAll('.number-val').forEach(animateCount);
            io.unobserve(e.target);
        }
    });
}, { threshold: 0.4 });

const nums = document.querySelector('.numbers-grid');
if (nums) io.observe(nums);

// Architecture diagram
function buildArchDiagram() {
    const el = document.getElementById('archDiagram');
    if (!el) return;

    el.innerHTML = `
    <svg width="100%" viewBox="0 0 800 380" xmlns="http://www.w3.org/2000/svg" style="max-height:380px">
      <defs>
        <marker id="arr" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
          <polygon points="0 0, 8 3, 0 6" fill="#333"/>
        </marker>
        <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#0070f3"/>
          <stop offset="100%" stop-color="#7928ca"/>
        </linearGradient>
      </defs>

      <!-- Input -->
      <rect x="30" y="155" width="120" height="50" rx="8" fill="#141414" stroke="#222" stroke-width="1"/>
      <text x="90" y="176" text-anchor="middle" fill="#a1a1aa" font-size="11" font-family="Inter,sans-serif" font-weight="600">Task Input</text>
      <text x="90" y="193" text-anchor="middle" fill="#555" font-size="10" font-family="Inter,sans-serif">"Analyze data"</text>

      <!-- Orchestrator -->
      <rect x="240" y="145" width="160" height="60" rx="8" fill="url(#grad)" opacity="0.9"/>
      <text x="320" y="169" text-anchor="middle" fill="#fff" font-size="12" font-family="Inter,sans-serif" font-weight="700">Orchestrator</text>
      <text x="320" y="186" text-anchor="middle" fill="rgba(255,255,255,0.7)" font-size="9.5" font-family="Inter,sans-serif">Task decomposition</text>
      <text x="320" y="199" text-anchor="middle" fill="rgba(255,255,255,0.7)" font-size="9.5" font-family="Inter,sans-serif">Model selection</text>

      <!-- arrow input -> orchestrator -->
      <line x1="150" y1="180" x2="240" y2="175" stroke="#333" stroke-width="1.5" marker-end="url(#arr)"/>

      <!-- Agents -->
      <rect x="100" y="280" width="110" height="50" rx="6" fill="#141414" stroke="#222" stroke-width="1"/>
      <text x="155" y="301" text-anchor="middle" fill="#f5f5f5" font-size="10.5" font-family="Inter,sans-serif" font-weight="600">Agent 1</text>
      <text x="155" y="315" text-anchor="middle" fill="#0070f3" font-size="9" font-family="Inter,sans-serif">Phi-3 Mini</text>
      <text x="155" y="327" text-anchor="middle" fill="#555" font-size="8.5" font-family="Inter,sans-serif">Reasoning</text>

      <rect x="285" y="280" width="110" height="50" rx="6" fill="#141414" stroke="#222" stroke-width="1"/>
      <text x="340" y="301" text-anchor="middle" fill="#f5f5f5" font-size="10.5" font-family="Inter,sans-serif" font-weight="600">Agent 2</text>
      <text x="340" y="315" text-anchor="middle" fill="#0070f3" font-size="9" font-family="Inter,sans-serif">TinyLlama</text>
      <text x="340" y="327" text-anchor="middle" fill="#555" font-size="8.5" font-family="Inter,sans-serif">Extraction</text>

      <rect x="470" y="280" width="110" height="50" rx="6" fill="#141414" stroke="#222" stroke-width="1"/>
      <text x="525" y="301" text-anchor="middle" fill="#f5f5f5" font-size="10.5" font-family="Inter,sans-serif" font-weight="600">Agent 3</text>
      <text x="525" y="315" text-anchor="middle" fill="#0070f3" font-size="9" font-family="Inter,sans-serif">Qwen2</text>
      <text x="525" y="327" text-anchor="middle" fill="#555" font-size="8.5" font-family="Inter,sans-serif">Analysis</text>

      <!-- arrows orchestrator -> agents -->
      <line x1="320" y1="205" x2="155" y2="280" stroke="#333" stroke-width="1.5" marker-end="url(#arr)"/>
      <line x1="320" y1="205" x2="340" y2="280" stroke="#333" stroke-width="1.5" marker-end="url(#arr)"/>
      <line x1="320" y1="205" x2="525" y2="280" stroke="#333" stroke-width="1.5" marker-end="url(#arr)"/>

      <!-- Aggregator -->
      <rect x="560" y="145" width="150" height="60" rx="8" fill="#141414" stroke="#0070f3" stroke-width="1.5"/>
      <text x="635" y="169" text-anchor="middle" fill="#f5f5f5" font-size="12" font-family="Inter,sans-serif" font-weight="700">Aggregator</text>
      <text x="635" y="186" text-anchor="middle" fill="#a1a1aa" font-size="9.5" font-family="Inter,sans-serif">Result synthesis</text>
      <text x="635" y="199" text-anchor="middle" fill="#0070f3" font-size="9.5" font-family="Inter,sans-serif">Gemma 2B</text>

      <!-- arrows agents -> aggregator -->
      <line x1="210" y1="305" x2="590" y2="205" stroke="#333" stroke-width="1.5" marker-end="url(#arr)"/>
      <line x1="395" y1="305" x2="610" y2="205" stroke="#333" stroke-width="1.5" marker-end="url(#arr)"/>
      <line x1="525" y1="280" x2="625" y2="205" stroke="#333" stroke-width="1.5" marker-end="url(#arr)"/>

      <!-- Time labels -->
      <text x="155" y="258" text-anchor="middle" fill="#555" font-size="9" font-family="Inter,sans-serif">8s</text>
      <text x="340" y="258" text-anchor="middle" fill="#555" font-size="9" font-family="Inter,sans-serif">6s</text>
      <text x="525" y="258" text-anchor="middle" fill="#555" font-size="9" font-family="Inter,sans-serif">7s</text>

      <!-- Total -->
      <text x="635" y="228" text-anchor="middle" fill="#a1a1aa" font-size="9" font-family="Inter,sans-serif">Total: 10s (parallel)</text>
      <text x="635" y="243" text-anchor="middle" fill="#10b981" font-size="10" font-family="Inter,sans-serif" font-weight="600">vs 45s sequential</text>
    </svg>`;
}

window.addEventListener('load', buildArchDiagram);

console.log('%cCH8 AGENT', 'color:#0070f3;font-size:18px;font-weight:700;');
console.log('%cAutonomous AI Orchestration\nhttps://github.com/hudsonrj/ch8-cluster-agent', 'color:#71717a;font-size:12px;');
