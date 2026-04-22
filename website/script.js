// Initialize particles.js with refined settings
particlesJS('particles-js', {
    particles: {
        number: {
            value: 60,
            density: {
                enable: true,
                value_area: 1000
            }
        },
        color: {
            value: '#00d4ff'
        },
        shape: {
            type: 'circle'
        },
        opacity: {
            value: 0.3,
            random: true,
            anim: {
                enable: true,
                speed: 0.5,
                opacity_min: 0.1,
                sync: false
            }
        },
        size: {
            value: 2.5,
            random: true,
            anim: {
                enable: true,
                speed: 2,
                size_min: 0.5,
                sync: false
            }
        },
        line_linked: {
            enable: true,
            distance: 120,
            color: '#00d4ff',
            opacity: 0.15,
            width: 1
        },
        move: {
            enable: true,
            speed: 1.5,
            direction: 'none',
            random: true,
            straight: false,
            out_mode: 'out',
            bounce: false
        }
    },
    interactivity: {
        detect_on: 'canvas',
        events: {
            onhover: {
                enable: true,
                mode: 'grab'
            },
            onclick: {
                enable: true,
                mode: 'push'
            },
            resize: true
        },
        modes: {
            grab: {
                distance: 140,
                line_linked: {
                    opacity: 0.3
                }
            },
            push: {
                particles_nb: 3
            }
        }
    },
    retina_detect: true
});

// Initialize AOS (Animate on Scroll) with refined settings
AOS.init({
    duration: 800,
    once: true,
    offset: 80,
    easing: 'ease-out-cubic'
});

// Tab functionality
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const tab = btn.dataset.tab;

        // Remove active class from all buttons and panes
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

        // Add active class to clicked button and corresponding pane
        btn.classList.add('active');
        document.getElementById(tab).classList.add('active');
    });
});

// Copy to clipboard functionality with better feedback
document.querySelectorAll('.copy-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const codeBlock = btn.previousElementSibling.querySelector('code');
        const text = codeBlock.textContent;

        navigator.clipboard.writeText(text).then(() => {
            const originalHTML = btn.innerHTML;
            btn.innerHTML = '<i class="fas fa-check"></i> Copied!';
            btn.style.background = 'rgba(16, 185, 129, 0.15)';
            btn.style.borderColor = '#10b981';
            btn.style.color = '#10b981';

            setTimeout(() => {
                btn.innerHTML = originalHTML;
                btn.style.background = '';
                btn.style.borderColor = '';
                btn.style.color = '';
            }, 2000);
        });
    });
});

// Smooth scroll for anchor links
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

// Mobile menu toggle with animation
const mobileMenuBtn = document.querySelector('.mobile-menu-btn');
const navLinks = document.querySelector('.nav-links');

if (mobileMenuBtn) {
    mobileMenuBtn.addEventListener('click', () => {
        const isOpen = navLinks.style.display === 'flex';
        navLinks.style.display = isOpen ? 'none' : 'flex';
        mobileMenuBtn.innerHTML = isOpen ? '<i class="fas fa-bars"></i>' : '<i class="fas fa-times"></i>';
    });
}

// Typing animation for hero title
const typingText = document.querySelector('.typing-text');
if (typingText) {
    const text = typingText.textContent;
    typingText.textContent = '';
    let i = 0;

    function typeWriter() {
        if (i < text.length) {
            typingText.textContent += text.charAt(i);
            i++;
            setTimeout(typeWriter, 80);
        }
    }

    setTimeout(typeWriter, 800);
}

// Animated cluster diagram
function createClusterAnimation() {
    const container = document.getElementById('clusterAnimation');
    if (!container) return;

    const svg = `
        <svg width="100%" height="100%" viewBox="0 0 600 480" xmlns="http://www.w3.org/2000/svg">
            <!-- Central Coordinator -->
            <g id="coordinator">
                <circle cx="300" cy="240" r="36" fill="url(#grad1)" class="pulse" stroke="rgba(0,212,255,0.3)" stroke-width="2">
                    <animate attributeName="r" values="36;40;36" dur="2.5s" repeatCount="indefinite"/>
                </circle>
                <text x="300" y="243" text-anchor="middle" fill="#fff" font-size="11" font-weight="bold" font-family="Inter, sans-serif">
                    Coordinator
                </text>
            </g>

            <!-- Worker Nodes -->
            <g id="worker1" class="worker-node">
                <circle cx="140" cy="100" r="28" fill="#6366f1" opacity="0.85" stroke="rgba(99,102,241,0.3)" stroke-width="2"/>
                <text x="140" y="104" text-anchor="middle" fill="#fff" font-size="9.5" font-family="Inter, sans-serif">
                    Pi 3
                </text>
                <line x1="140" y1="128" x2="300" y2="240" stroke="#00d4ff" stroke-width="1.5" opacity="0.4">
                    <animate attributeName="opacity" values="0.15;0.7;0.15" dur="3.5s" repeatCount="indefinite"/>
                </line>
            </g>

            <g id="worker2" class="worker-node">
                <circle cx="460" cy="100" r="28" fill="#6366f1" opacity="0.85" stroke="rgba(99,102,241,0.3)" stroke-width="2"/>
                <text x="460" y="104" text-anchor="middle" fill="#fff" font-size="9.5" font-family="Inter, sans-serif">
                    Laptop
                </text>
                <line x1="460" y1="128" x2="300" y2="240" stroke="#00d4ff" stroke-width="1.5" opacity="0.4">
                    <animate attributeName="opacity" values="0.15;0.7;0.15" dur="3.5s" repeatCount="indefinite" begin="0.6s"/>
                </line>
            </g>

            <g id="worker3" class="worker-node">
                <circle cx="140" cy="380" r="28" fill="#6366f1" opacity="0.85" stroke="rgba(99,102,241,0.3)" stroke-width="2"/>
                <text x="140" y="384" text-anchor="middle" fill="#fff" font-size="9.5" font-family="Inter, sans-serif">
                    Android
                </text>
                <line x1="140" y1="352" x2="300" y2="240" stroke="#00d4ff" stroke-width="1.5" opacity="0.4">
                    <animate attributeName="opacity" values="0.15;0.7;0.15" dur="3.5s" repeatCount="indefinite" begin="1.2s"/>
                </line>
            </g>

            <g id="worker4" class="worker-node">
                <circle cx="460" cy="380" r="28" fill="#6366f1" opacity="0.85" stroke="rgba(99,102,241,0.3)" stroke-width="2"/>
                <text x="460" y="384" text-anchor="middle" fill="#fff" font-size="9.5" font-family="Inter, sans-serif">
                    Pi Zero
                </text>
                <line x1="460" y1="352" x2="300" y2="240" stroke="#00d4ff" stroke-width="1.5" opacity="0.4">
                    <animate attributeName="opacity" values="0.15;0.7;0.15" dur="3.5s" repeatCount="indefinite" begin="1.8s"/>
                </line>
            </g>

            <!-- Gradient definitions -->
            <defs>
                <radialGradient id="grad1">
                    <stop offset="0%" style="stop-color:#00d4ff;stop-opacity:1" />
                    <stop offset="100%" style="stop-color:#6366f1;stop-opacity:1" />
                </radialGradient>
            </defs>
        </svg>
    `;

    container.innerHTML = svg;
}

// Architecture diagram animation
function createArchDiagram() {
    const container = document.getElementById('archDiagram');
    if (!container) return;

    const svg = `
        <svg width="100%" height="100%" viewBox="0 0 800 580" xmlns="http://www.w3.org/2000/svg">
            <!-- Task Input -->
            <g id="task-input">
                <rect x="50" y="50" width="140" height="70" rx="8" fill="#1a1d29" stroke="#00d4ff" stroke-width="1.5"/>
                <text x="120" y="78" text-anchor="middle" fill="#fff" font-size="13" font-weight="600" font-family="Inter, sans-serif">Task Input</text>
                <text x="120" y="96" text-anchor="middle" fill="#94a3b8" font-size="11" font-family="Inter, sans-serif">"Analyze data"</text>
            </g>

            <!-- Orchestrator -->
            <g id="orchestrator">
                <rect x="310" y="50" width="180" height="70" rx="8" fill="#1a1d29" stroke="#6366f1" stroke-width="2"/>
                <text x="400" y="74" text-anchor="middle" fill="#fff" font-size="14" font-weight="700" font-family="Inter, sans-serif">Orchestrator</text>
                <text x="400" y="91" text-anchor="middle" fill="#94a3b8" font-size="10.5" font-family="Inter, sans-serif">Task Decomposition</text>
                <text x="400" y="106" text-anchor="middle" fill="#94a3b8" font-size="10.5" font-family="Inter, sans-serif">Model Selection</text>
            </g>

            <!-- Arrow 1 -->
            <line x1="190" y1="85" x2="310" y2="85" stroke="#00d4ff" stroke-width="2" marker-end="url(#arrowhead)"/>

            <!-- Small Models (Parallel) -->
            <g id="models">
                <rect x="100" y="240" width="110" height="55" rx="7" fill="#1a1d29" stroke="#00d4ff" stroke-width="1.5"/>
                <text x="155" y="262" text-anchor="middle" fill="#fff" font-size="11.5" font-weight="600" font-family="Inter, sans-serif">Phi-3 Mini</text>
                <text x="155" y="276" text-anchor="middle" fill="#00d4ff" font-size="9.5" font-weight="600" font-family="Inter, sans-serif">0.5B</text>
                <text x="155" y="289" text-anchor="middle" fill="#94a3b8" font-size="9.5" font-family="Inter, sans-serif">Reasoning</text>

                <rect x="285" y="240" width="110" height="55" rx="7" fill="#1a1d29" stroke="#00d4ff" stroke-width="1.5"/>
                <text x="340" y="262" text-anchor="middle" fill="#fff" font-size="11.5" font-weight="600" font-family="Inter, sans-serif">TinyLlama</text>
                <text x="340" y="276" text-anchor="middle" fill="#00d4ff" font-size="9.5" font-weight="600" font-family="Inter, sans-serif">1.1B</text>
                <text x="340" y="289" text-anchor="middle" fill="#94a3b8" font-size="9.5" font-family="Inter, sans-serif">Code</text>

                <rect x="470" y="240" width="110" height="55" rx="7" fill="#1a1d29" stroke="#00d4ff" stroke-width="1.5"/>
                <text x="525" y="262" text-anchor="middle" fill="#fff" font-size="11.5" font-weight="600" font-family="Inter, sans-serif">Qwen2</text>
                <text x="525" y="276" text-anchor="middle" fill="#00d4ff" font-size="9.5" font-weight="600" font-family="Inter, sans-serif">0.5B</text>
                <text x="525" y="289" text-anchor="middle" fill="#94a3b8" font-size="9.5" font-family="Inter, sans-serif">Extract</text>
            </g>

            <!-- Arrows to models -->
            <line x1="400" y1="120" x2="155" y2="240" stroke="#6366f1" stroke-width="1.5" marker-end="url(#arrowhead)"/>
            <line x1="400" y1="120" x2="340" y2="240" stroke="#6366f1" stroke-width="1.5" marker-end="url(#arrowhead)"/>
            <line x1="400" y1="120" x2="525" y2="240" stroke="#6366f1" stroke-width="1.5" marker-end="url(#arrowhead)"/>

            <!-- Aggregator -->
            <g id="aggregator">
                <rect x="310" y="410" width="180" height="70" rx="8" fill="#1a1d29" stroke="#ec4899" stroke-width="2"/>
                <text x="400" y="434" text-anchor="middle" fill="#fff" font-size="14" font-weight="700" font-family="Inter, sans-serif">Aggregator</text>
                <text x="400" y="450" text-anchor="middle" fill="#94a3b8" font-size="10.5" font-family="Inter, sans-serif">Result Synthesis</text>
                <text x="400" y="466" text-anchor="middle" fill="#00d4ff" font-size="10.5" font-weight="600" font-family="Inter, sans-serif">Gemma 2B</text>
            </g>

            <!-- Arrows to aggregator -->
            <line x1="155" y1="295" x2="310" y2="445" stroke="#00d4ff" stroke-width="1.5" marker-end="url(#arrowhead)"/>
            <line x1="340" y1="295" x2="380" y2="410" stroke="#00d4ff" stroke-width="1.5" marker-end="url(#arrowhead)"/>
            <line x1="525" y1="295" x2="420" y2="410" stroke="#00d4ff" stroke-width="1.5" marker-end="url(#arrowhead)"/>

            <!-- Output -->
            <g id="output">
                <rect x="610" y="410" width="140" height="70" rx="8" fill="#1a1d29" stroke="#00d4ff" stroke-width="1.5"/>
                <text x="680" y="433" text-anchor="middle" fill="#fff" font-size="13" font-weight="600" font-family="Inter, sans-serif">Final Result</text>
                <text x="680" y="451" text-anchor="middle" fill="#00d4ff" font-size="10.5" font-family="Inter, sans-serif">High Quality</text>
                <text x="680" y="466" text-anchor="middle" fill="#00d4ff" font-size="10.5" font-family="Inter, sans-serif">Less Tokens</text>
            </g>

            <!-- Arrow to output -->
            <line x1="490" y1="445" x2="610" y2="445" stroke="#ec4899" stroke-width="2" marker-end="url(#arrowhead)"/>

            <!-- Arrow marker -->
            <defs>
                <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
                    <polygon points="0 0, 10 3, 0 6" fill="#00d4ff" />
                </marker>
            </defs>

            <!-- Time annotations -->
            <text x="155" y="318" text-anchor="middle" fill="#00d4ff" font-size="10" font-weight="600" font-family="Inter, sans-serif">8s</text>
            <text x="340" y="318" text-anchor="middle" fill="#00d4ff" font-size="10" font-weight="600" font-family="Inter, sans-serif">6s</text>
            <text x="525" y="318" text-anchor="middle" fill="#00d4ff" font-size="10" font-weight="600" font-family="Inter, sans-serif">7s</text>
            <text x="400" y="505" text-anchor="middle" fill="#ec4899" font-size="10" font-weight="600" font-family="Inter, sans-serif">2s aggregation</text>
            <text x="400" y="525" text-anchor="middle" fill="#fff" font-size="13" font-weight="700" font-family="Inter, sans-serif">Total: 10s (parallel!)</text>
        </svg>
    `;

    container.innerHTML = svg;
}

// Initialize animations when page loads
window.addEventListener('load', () => {
    createClusterAnimation();
    createArchDiagram();
});

// Navbar scroll effect
let lastScroll = 0;
const navbar = document.querySelector('.navbar');

window.addEventListener('scroll', () => {
    const currentScroll = window.pageYOffset;

    if (currentScroll > 50) {
        navbar.classList.add('scrolled');
    } else {
        navbar.classList.remove('scrolled');
    }

    lastScroll = currentScroll;
});

// Animated counter for stats
function animateValue(element, start, end, duration) {
    let startTimestamp = null;
    const step = (timestamp) => {
        if (!startTimestamp) startTimestamp = timestamp;
        const progress = Math.min((timestamp - startTimestamp) / duration, 1);
        const value = Math.floor(progress * (end - start) + start);
        const text = element.textContent;

        if (text.includes('%')) {
            element.textContent = value + '%';
        } else if (text.includes('x')) {
            element.textContent = value + 'x';
        } else if (text.includes('+')) {
            element.textContent = value + '+';
        } else {
            element.textContent = value;
        }

        if (progress < 1) {
            window.requestAnimationFrame(step);
        }
    };
    window.requestAnimationFrame(step);
}

// Observe stats section and trigger animation
const statsObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            document.querySelectorAll('.stat-number').forEach(stat => {
                const text = stat.textContent;
                const match = text.match(/\d+/);
                if (match) {
                    const num = parseInt(match[0]);
                    animateValue(stat, 0, num, 2000);
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

// Console easter egg with refined styling
console.log(`
%c   _____ _    _  ___
  / ____| |  | |/ _ \\
 | |    | |__| | (_) |
 | |    |  __  |> _ <
 | |____| |  | | (_) |
  \\_____!_|  |_|\\___/

%c CH8 AGENT - Democratic Distributed AI
%c https://github.com/hudsonrj/ch8-cluster-agent

`, 'color: #00d4ff; font-family: monospace; font-size: 12px;', 'color: #6366f1; font-weight: bold; font-size: 14px;', 'color: #94a3b8; font-size: 12px;');

console.log('%cInterested in the code? Check out our GitHub! 🚀', 'color: #00d4ff; font-size: 13px; font-weight: bold;');

// Parallax effect for hero section
window.addEventListener('scroll', () => {
    const scrolled = window.pageYOffset;
    const heroVisual = document.querySelector('.hero-visual');
    if (heroVisual) {
        heroVisual.style.transform = `translateY(${scrolled * 0.3}px)`;
    }
});

// Add loading animation
window.addEventListener('load', () => {
    document.body.classList.add('loaded');
});

// Smooth reveal animation for sections
const revealObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.classList.add('revealed');
        }
    });
}, { threshold: 0.1 });

document.querySelectorAll('section').forEach(section => {
    revealObserver.observe(section);
});
