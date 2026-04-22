// Minimal particles - very subtle
particlesJS('particles-js', {
    particles: {
        number: {
            value: 30,
            density: {
                enable: true,
                value_area: 1500
            }
        },
        color: {
            value: '#0066ff'
        },
        shape: {
            type: 'circle'
        },
        opacity: {
            value: 0.15,
            random: true
        },
        size: {
            value: 2,
            random: true
        },
        line_linked: {
            enable: true,
            distance: 150,
            color: '#0066ff',
            opacity: 0.08,
            width: 1
        },
        move: {
            enable: true,
            speed: 1,
            direction: 'none',
            random: true,
            straight: false,
            out_mode: 'out'
        }
    },
    interactivity: {
        detect_on: 'canvas',
        events: {
            onhover: {
                enable: false
            },
            onclick: {
                enable: false
            },
            resize: true
        }
    },
    retina_detect: true
});

// Initialize AOS with minimal settings
AOS.init({
    duration: 600,
    once: true,
    offset: 50,
    easing: 'ease-out'
});

// Tab functionality
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const tab = btn.dataset.tab;

        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

        btn.classList.add('active');
        const pane = document.getElementById(tab);
        if (pane) pane.classList.add('active');
    });
});

// Copy to clipboard
document.querySelectorAll('.copy-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const codeBlock = btn.previousElementSibling.querySelector('code');
        const text = codeBlock.textContent;

        navigator.clipboard.writeText(text).then(() => {
            const originalHTML = btn.innerHTML;
            btn.innerHTML = '✓ Copied';
            btn.style.background = 'rgba(0, 212, 129, 0.2)';

            setTimeout(() => {
                btn.innerHTML = originalHTML;
                btn.style.background = '';
            }, 2000);
        });
    });
});

// Smooth scroll
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            const offset = 80;
            const targetPosition = target.offsetTop - offset;
            window.scrollTo({
                top: targetPosition,
                behavior: 'smooth'
            });
        }
    });
});

// Mobile menu toggle
const mobileMenuBtn = document.querySelector('.mobile-menu-btn');
const navLinks = document.querySelector('.nav-links');

if (mobileMenuBtn && navLinks) {
    mobileMenuBtn.addEventListener('click', () => {
        const isOpen = navLinks.style.display === 'flex';
        navLinks.style.display = isOpen ? 'none' : 'flex';
        mobileMenuBtn.innerHTML = isOpen ? '<i class="fas fa-bars"></i>' : '<i class="fas fa-times"></i>';
    });
}

// Create cluster animation - minimal style
function createClusterAnimation() {
    const container = document.getElementById('clusterAnimation');
    if (!container) return;

    const svg = `
        <svg width="100%" height="100%" viewBox="0 0 600 400" xmlns="http://www.w3.org/2000/svg">
            <!-- Central Coordinator -->
            <g id="coordinator">
                <circle cx="300" cy="200" r="32" fill="#0066ff" opacity="0.9" stroke="#e5e5e5" stroke-width="1"/>
                <text x="300" y="205" text-anchor="middle" fill="#ffffff" font-size="10" font-weight="600" font-family="system-ui">
                    Coordinator
                </text>
            </g>

            <!-- Worker Nodes -->
            <g id="worker1">
                <circle cx="150" cy="80" r="24" fill="#ffffff" stroke="#e5e5e5" stroke-width="1"/>
                <text x="150" y="84" text-anchor="middle" fill="#666666" font-size="9" font-family="system-ui">Pi 3</text>
                <line x1="150" y1="104" x2="300" y2="200" stroke="#e5e5e5" stroke-width="1"/>
            </g>

            <g id="worker2">
                <circle cx="450" cy="80" r="24" fill="#ffffff" stroke="#e5e5e5" stroke-width="1"/>
                <text x="450" y="84" text-anchor="middle" fill="#666666" font-size="9" font-family="system-ui">Laptop</text>
                <line x1="450" y1="104" x2="300" y2="200" stroke="#e5e5e5" stroke-width="1"/>
            </g>

            <g id="worker3">
                <circle cx="150" cy="320" r="24" fill="#ffffff" stroke="#e5e5e5" stroke-width="1"/>
                <text x="150" y="324" text-anchor="middle" fill="#666666" font-size="9" font-family="system-ui">Android</text>
                <line x1="150" y1="296" x2="300" y2="200" stroke="#e5e5e5" stroke-width="1"/>
            </g>

            <g id="worker4">
                <circle cx="450" cy="320" r="24" fill="#ffffff" stroke="#e5e5e5" stroke-width="1"/>
                <text x="450" y="324" text-anchor="middle" fill="#666666" font-size="9" font-family="system-ui">Pi Zero</text>
                <line x1="450" y1="296" x2="300" y2="200" stroke="#e5e5e5" stroke-width="1"/>
            </g>
        </svg>
    `;

    container.innerHTML = svg;
}

// Architecture diagram - clean style
function createArchDiagram() {
    const container = document.getElementById('archDiagram');
    if (!container) return;

    const svg = `
        <svg width="100%" height="100%" viewBox="0 0 800 500" xmlns="http://www.w3.org/2000/svg">
            <!-- Task Input -->
            <rect x="50" y="50" width="120" height="60" rx="6" fill="#ffffff" stroke="#e5e5e5" stroke-width="1"/>
            <text x="110" y="75" text-anchor="middle" fill="#0a0a0a" font-size="11" font-weight="600" font-family="system-ui">Task Input</text>
            <text x="110" y="91" text-anchor="middle" fill="#999999" font-size="9" font-family="system-ui">"Analyze data"</text>

            <!-- Orchestrator -->
            <rect x="280" y="50" width="160" height="60" rx="6" fill="#0066ff" stroke="#e5e5e5" stroke-width="1"/>
            <text x="360" y="73" text-anchor="middle" fill="#ffffff" font-size="12" font-weight="600" font-family="system-ui">Orchestrator</text>
            <text x="360" y="88" text-anchor="middle" fill="rgba(255,255,255,0.8)" font-size="9" font-family="system-ui">Task Decomposition</text>
            <text x="360" y="100" text-anchor="middle" fill="rgba(255,255,255,0.8)" font-size="9" font-family="system-ui">Model Selection</text>

            <!-- Arrow 1 -->
            <line x1="170" y1="80" x2="280" y2="80" stroke="#e5e5e5" stroke-width="1.5" marker-end="url(#arrow)"/>

            <!-- Small Models -->
            <rect x="100" y="200" width="100" height="50" rx="5" fill="#ffffff" stroke="#e5e5e5" stroke-width="1"/>
            <text x="150" y="219" text-anchor="middle" fill="#0a0a0a" font-size="10" font-weight="600" font-family="system-ui">Phi-3 Mini</text>
            <text x="150" y="232" text-anchor="middle" fill="#0066ff" font-size="9" font-family="system-ui">0.5B</text>
            <text x="150" y="244" text-anchor="middle" fill="#999999" font-size="8" font-family="system-ui">Reasoning</text>

            <rect x="270" y="200" width="100" height="50" rx="5" fill="#ffffff" stroke="#e5e5e5" stroke-width="1"/>
            <text x="320" y="219" text-anchor="middle" fill="#0a0a0a" font-size="10" font-weight="600" font-family="system-ui">TinyLlama</text>
            <text x="320" y="232" text-anchor="middle" fill="#0066ff" font-size="9" font-family="system-ui">1.1B</text>
            <text x="320" y="244" text-anchor="middle" fill="#999999" font-size="8" font-family="system-ui">Code</text>

            <rect x="440" y="200" width="100" height="50" rx="5" fill="#ffffff" stroke="#e5e5e5" stroke-width="1"/>
            <text x="490" y="219" text-anchor="middle" fill="#0a0a0a" font-size="10" font-weight="600" font-family="system-ui">Qwen2</text>
            <text x="490" y="232" text-anchor="middle" fill="#0066ff" font-size="9" font-family="system-ui">0.5B</text>
            <text x="490" y="244" text-anchor="middle" fill="#999999" font-size="8" font-family="system-ui">Extract</text>

            <!-- Arrows to models -->
            <line x1="360" y1="110" x2="150" y2="200" stroke="#e5e5e5" stroke-width="1.5" marker-end="url(#arrow)"/>
            <line x1="360" y1="110" x2="320" y2="200" stroke="#e5e5e5" stroke-width="1.5" marker-end="url(#arrow)"/>
            <line x1="360" y1="110" x2="490" y2="200" stroke="#e5e5e5" stroke-width="1.5" marker-end="url(#arrow)"/>

            <!-- Aggregator -->
            <rect x="280" y="350" width="160" height="60" rx="6" fill="#ffffff" stroke="#0066ff" stroke-width="2"/>
            <text x="360" y="372" text-anchor="middle" fill="#0a0a0a" font-size="12" font-weight="600" font-family="system-ui">Aggregator</text>
            <text x="360" y="387" text-anchor="middle" fill="#666666" font-size="9" font-family="system-ui">Result Synthesis</text>
            <text x="360" y="400" text-anchor="middle" fill="#0066ff" font-size="9" font-family="system-ui">Gemma 2B</text>

            <!-- Arrows to aggregator -->
            <line x1="150" y1="250" x2="300" y2="350" stroke="#e5e5e5" stroke-width="1.5" marker-end="url(#arrow)"/>
            <line x1="320" y1="250" x2="350" y2="350" stroke="#e5e5e5" stroke-width="1.5" marker-end="url(#arrow)"/>
            <line x1="490" y1="250" x2="420" y2="350" stroke="#e5e5e5" stroke-width="1.5" marker-end="url(#arrow)"/>

            <!-- Output -->
            <rect x="580" y="350" width="120" height="60" rx="6" fill="#ffffff" stroke="#e5e5e5" stroke-width="1"/>
            <text x="640" y="372" text-anchor="middle" fill="#0a0a0a" font-size="11" font-weight="600" font-family="system-ui">Final Result</text>
            <text x="640" y="387" text-anchor="middle" fill="#0066ff" font-size="9" font-family="system-ui">High Quality</text>
            <text x="640" y="399" text-anchor="middle" fill="#0066ff" font-size="9" font-family="system-ui">Less Tokens</text>

            <!-- Arrow to output -->
            <line x1="440" y1="380" x2="580" y2="380" stroke="#e5e5e5" stroke-width="1.5" marker-end="url(#arrow)"/>

            <!-- Arrow marker -->
            <defs>
                <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
                    <polygon points="0 0, 8 3, 0 6" fill="#e5e5e5" />
                </marker>
            </defs>

            <!-- Time annotations -->
            <text x="150" y="270" text-anchor="middle" fill="#666666" font-size="9" font-weight="500" font-family="system-ui">8s</text>
            <text x="320" y="270" text-anchor="middle" fill="#666666" font-size="9" font-weight="500" font-family="system-ui">6s</text>
            <text x="490" y="270" text-anchor="middle" fill="#666666" font-size="9" font-weight="500" font-family="system-ui">7s</text>
            <text x="360" y="430" text-anchor="middle" fill="#999999" font-size="9" font-family="system-ui">2s aggregation</text>
            <text x="360" y="445" text-anchor="middle" fill="#0a0a0a" font-size="11" font-weight="600" font-family="system-ui">Total: 10s (parallel!)</text>
        </svg>
    `;

    container.innerHTML = svg;
}

// Initialize diagrams
window.addEventListener('load', () => {
    createClusterAnimation();
    createArchDiagram();
});

// Minimal navbar scroll effect
window.addEventListener('scroll', () => {
    const navbar = document.querySelector('.navbar');
    if (window.scrollY > 50) {
        navbar.style.boxShadow = '0 1px 3px rgba(0, 0, 0, 0.08)';
    } else {
        navbar.style.boxShadow = 'none';
    }
});

// Animated counter
function animateValue(element, start, end, duration) {
    let startTimestamp = null;
    const step = (timestamp) => {
        if (!startTimestamp) startTimestamp = timestamp;
        const progress = Math.min((timestamp - startTimestamp) / duration, 1);
        const value = Math.floor(progress * (end - start) + start);
        const text = element.getAttribute('data-original');

        if (text && text.includes('%')) {
            element.textContent = value + '%';
        } else if (text && text.includes('x')) {
            element.textContent = value + 'x';
        } else if (text && text.includes('B')) {
            element.textContent = text;
        } else {
            element.textContent = value;
        }

        if (progress < 1) {
            window.requestAnimationFrame(step);
        }
    };
    window.requestAnimationFrame(step);
}

// Observe stats
const statsObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            document.querySelectorAll('.stat-number').forEach(stat => {
                const text = stat.textContent;
                stat.setAttribute('data-original', text);
                const match = text.match(/\d+/);
                if (match) {
                    const num = parseInt(match[0]);
                    animateValue(stat, 0, num, 1500);
                }
            });
            statsObserver.unobserve(entry.target);
        }
    });
}, { threshold: 0.3 });

const statsSection = document.querySelector('.hero-stats');
if (statsSection) {
    statsObserver.observe(statsSection);
}

// Minimal console easter egg
console.log(
    '%cCH8 AGENT%c\nDemocratic Distributed AI\nhttps://github.com/hudsonrj/ch8-cluster-agent',
    'color: #0066ff; font-size: 16px; font-weight: 600;',
    'color: #666666; font-size: 12px;'
);
