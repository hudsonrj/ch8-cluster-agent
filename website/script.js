// Initialize particles.js
particlesJS('particles-js', {
    particles: {
        number: {
            value: 80,
            density: {
                enable: true,
                value_area: 800
            }
        },
        color: {
            value: '#00f2ff'
        },
        shape: {
            type: 'circle'
        },
        opacity: {
            value: 0.5,
            random: false
        },
        size: {
            value: 3,
            random: true
        },
        line_linked: {
            enable: true,
            distance: 150,
            color: '#00f2ff',
            opacity: 0.2,
            width: 1
        },
        move: {
            enable: true,
            speed: 2,
            direction: 'none',
            random: false,
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
                mode: 'repulse'
            },
            onclick: {
                enable: true,
                mode: 'push'
            },
            resize: true
        }
    },
    retina_detect: true
});

// Initialize AOS (Animate on Scroll)
AOS.init({
    duration: 1000,
    once: true,
    offset: 100
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

// Copy to clipboard functionality
document.querySelectorAll('.copy-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const codeBlock = btn.previousElementSibling.querySelector('code');
        const text = codeBlock.textContent;

        navigator.clipboard.writeText(text).then(() => {
            btn.innerHTML = '<i class="fas fa-check"></i>';
            setTimeout(() => {
                btn.innerHTML = '<i class="fas fa-copy"></i>';
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
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});

// Mobile menu toggle
document.querySelector('.mobile-menu-btn').addEventListener('click', () => {
    const navLinks = document.querySelector('.nav-links');
    navLinks.style.display = navLinks.style.display === 'flex' ? 'none' : 'flex';
});

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
            setTimeout(typeWriter, 100);
        }
    }

    setTimeout(typeWriter, 1000);
}

// Animated cluster diagram
function createClusterAnimation() {
    const container = document.getElementById('clusterAnimation');
    if (!container) return;

    const svg = `
        <svg width="100%" height="100%" viewBox="0 0 600 500" xmlns="http://www.w3.org/2000/svg">
            <!-- Central Coordinator -->
            <g id="coordinator">
                <circle cx="300" cy="250" r="40" fill="url(#grad1)" class="pulse">
                    <animate attributeName="r" values="40;45;40" dur="2s" repeatCount="indefinite"/>
                </circle>
                <text x="300" y="255" text-anchor="middle" fill="#fff" font-size="12" font-weight="bold">
                    Coordinator
                </text>
            </g>

            <!-- Worker Nodes -->
            <g id="worker1" class="worker-node">
                <circle cx="150" cy="100" r="30" fill="#7000ff" opacity="0.8"/>
                <text x="150" y="105" text-anchor="middle" fill="#fff" font-size="10">
                    Pi 3
                </text>
                <line x1="150" y1="130" x2="300" y2="250" stroke="#00f2ff" stroke-width="2" opacity="0.5">
                    <animate attributeName="opacity" values="0.2;0.8;0.2" dur="3s" repeatCount="indefinite"/>
                </line>
            </g>

            <g id="worker2" class="worker-node">
                <circle cx="450" cy="100" r="30" fill="#7000ff" opacity="0.8"/>
                <text x="450" y="105" text-anchor="middle" fill="#fff" font-size="10">
                    Laptop
                </text>
                <line x1="450" y1="130" x2="300" y2="250" stroke="#00f2ff" stroke-width="2" opacity="0.5">
                    <animate attributeName="opacity" values="0.2;0.8;0.2" dur="3s" repeatCount="indefinite" begin="0.5s"/>
                </line>
            </g>

            <g id="worker3" class="worker-node">
                <circle cx="150" cy="400" r="30" fill="#7000ff" opacity="0.8"/>
                <text x="150" y="405" text-anchor="middle" fill="#fff" font-size="10">
                    Android
                </text>
                <line x1="150" y1="370" x2="300" y2="250" stroke="#00f2ff" stroke-width="2" opacity="0.5">
                    <animate attributeName="opacity" values="0.2;0.8;0.2" dur="3s" repeatCount="indefinite" begin="1s"/>
                </line>
            </g>

            <g id="worker4" class="worker-node">
                <circle cx="450" cy="400" r="30" fill="#7000ff" opacity="0.8"/>
                <text x="450" y="405" text-anchor="middle" fill="#fff" font-size="10">
                    Pi Zero
                </text>
                <line x1="450" y1="370" x2="300" y2="250" stroke="#00f2ff" stroke-width="2" opacity="0.5">
                    <animate attributeName="opacity" values="0.2;0.8;0.2" dur="3s" repeatCount="indefinite" begin="1.5s"/>
                </line>
            </g>

            <!-- Gradient definitions -->
            <defs>
                <radialGradient id="grad1">
                    <stop offset="0%" style="stop-color:#00f2ff;stop-opacity:1" />
                    <stop offset="100%" style="stop-color:#7000ff;stop-opacity:1" />
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
        <svg width="100%" height="100%" viewBox="0 0 800 600" xmlns="http://www.w3.org/2000/svg">
            <!-- Task Input -->
            <g id="task-input">
                <rect x="50" y="50" width="150" height="80" rx="10" fill="#131826" stroke="#00f2ff" stroke-width="2"/>
                <text x="125" y="80" text-anchor="middle" fill="#fff" font-size="14">Task Input</text>
                <text x="125" y="100" text-anchor="middle" fill="#a0aec0" font-size="12">"Analyze data"</text>
            </g>

            <!-- Orchestrator -->
            <g id="orchestrator">
                <rect x="300" y="50" width="200" height="80" rx="10" fill="#131826" stroke="#7000ff" stroke-width="3"/>
                <text x="400" y="75" text-anchor="middle" fill="#fff" font-size="16" font-weight="bold">Orchestrator</text>
                <text x="400" y="95" text-anchor="middle" fill="#a0aec0" font-size="12">Task Decomposition</text>
                <text x="400" y="110" text-anchor="middle" fill="#a0aec0" font-size="12">Model Selection</text>
            </g>

            <!-- Arrow 1 -->
            <line x1="200" y1="90" x2="300" y2="90" stroke="#00f2ff" stroke-width="2" marker-end="url(#arrowhead)">
                <animate attributeName="stroke-dashoffset" values="20;0" dur="2s" repeatCount="indefinite"/>
            </line>

            <!-- Small Models (Parallel) -->
            <g id="models">
                <rect x="100" y="250" width="120" height="60" rx="8" fill="#131826" stroke="#00f2ff" stroke-width="2"/>
                <text x="160" y="275" text-anchor="middle" fill="#fff" font-size="12">Phi-3 Mini</text>
                <text x="160" y="290" text-anchor="middle" fill="#00f2ff" font-size="10">0.5B</text>
                <text x="160" y="303" text-anchor="middle" fill="#a0aec0" font-size="10">Reasoning</text>

                <rect x="280" y="250" width="120" height="60" rx="8" fill="#131826" stroke="#00f2ff" stroke-width="2"/>
                <text x="340" y="275" text-anchor="middle" fill="#fff" font-size="12">TinyLlama</text>
                <text x="340" y="290" text-anchor="middle" fill="#00f2ff" font-size="10">1.1B</text>
                <text x="340" y="303" text-anchor="middle" fill="#a0aec0" font-size="10">Code</text>

                <rect x="460" y="250" width="120" height="60" rx="8" fill="#131826" stroke="#00f2ff" stroke-width="2"/>
                <text x="520" y="275" text-anchor="middle" fill="#fff" font-size="12">Qwen2</text>
                <text x="520" y="290" text-anchor="middle" fill="#00f2ff" font-size="10">0.5B</text>
                <text x="520" y="303" text-anchor="middle" fill="#a0aec0" font-size="10">Extract</text>
            </g>

            <!-- Arrows to models -->
            <line x1="400" y1="130" x2="160" y2="250" stroke="#7000ff" stroke-width="2" marker-end="url(#arrowhead)"/>
            <line x1="400" y1="130" x2="340" y2="250" stroke="#7000ff" stroke-width="2" marker-end="url(#arrowhead)"/>
            <line x1="400" y1="130" x2="520" y2="250" stroke="#7000ff" stroke-width="2" marker-end="url(#arrowhead)"/>

            <!-- Aggregator -->
            <g id="aggregator">
                <rect x="300" y="400" width="200" height="80" rx="10" fill="#131826" stroke="#ff00ff" stroke-width="3"/>
                <text x="400" y="425" text-anchor="middle" fill="#fff" font-size="16" font-weight="bold">Aggregator</text>
                <text x="400" y="445" text-anchor="middle" fill="#a0aec0" font-size="12">Result Synthesis</text>
                <text x="400" y="460" text-anchor="middle" fill="#00f2ff" font-size="12">Gemma 2B</text>
            </g>

            <!-- Arrows to aggregator -->
            <line x1="160" y1="310" x2="300" y2="440" stroke="#00f2ff" stroke-width="2" marker-end="url(#arrowhead)"/>
            <line x1="340" y1="310" x2="380" y2="400" stroke="#00f2ff" stroke-width="2" marker-end="url(#arrowhead)"/>
            <line x1="520" y1="310" x2="500" y2="400" stroke="#00f2ff" stroke-width="2" marker-end="url(#arrowhead)"/>

            <!-- Output -->
            <g id="output">
                <rect x="600" y="400" width="150" height="80" rx="10" fill="#131826" stroke="#00f2ff" stroke-width="2"/>
                <text x="675" y="425" text-anchor="middle" fill="#fff" font-size="14">Final Result</text>
                <text x="675" y="445" text-anchor="middle" fill="#00f2ff" font-size="12">High Quality</text>
                <text x="675" y="460" text-anchor="middle" fill="#00f2ff" font-size="12">Less Tokens</text>
            </g>

            <!-- Arrow to output -->
            <line x1="500" y1="440" x2="600" y2="440" stroke="#ff00ff" stroke-width="2" marker-end="url(#arrowhead)"/>

            <!-- Arrow marker -->
            <defs>
                <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
                    <polygon points="0 0, 10 3, 0 6" fill="#00f2ff" />
                </marker>
            </defs>

            <!-- Time annotations -->
            <text x="160" y="330" text-anchor="middle" fill="#00f2ff" font-size="11">8s</text>
            <text x="340" y="330" text-anchor="middle" fill="#00f2ff" font-size="11">6s</text>
            <text x="520" y="330" text-anchor="middle" fill="#00f2ff" font-size="11">7s</text>
            <text x="400" y="500" text-anchor="middle" fill="#ff00ff" font-size="11">2s aggregation</text>
            <text x="400" y="515" text-anchor="middle" fill="#fff" font-size="14" font-weight="bold">Total: 10s (parallel!)</text>
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
window.addEventListener('scroll', () => {
    const navbar = document.querySelector('.navbar');
    if (window.scrollY > 50) {
        navbar.style.background = 'rgba(10, 14, 26, 0.95)';
        navbar.style.boxShadow = '0 4px 20px rgba(0, 0, 0, 0.3)';
    } else {
        navbar.style.background = 'rgba(10, 14, 26, 0.9)';
        navbar.style.boxShadow = 'none';
    }
});

// Animated counter for stats
function animateValue(element, start, end, duration) {
    let startTimestamp = null;
    const step = (timestamp) => {
        if (!startTimestamp) startTimestamp = timestamp;
        const progress = Math.min((timestamp - startTimestamp) / duration, 1);
        const value = Math.floor(progress * (end - start) + start);
        element.textContent = value;
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
                if (text.includes('%')) {
                    const num = parseInt(text);
                    animateValue(stat, 0, num, 2000);
                    stat.textContent += '%';
                }
            });
            statsObserver.unobserve(entry.target);
        }
    });
});

const statsSection = document.querySelector('.hero-stats');
if (statsSection) {
    statsObserver.observe(statsSection);
}

// Console easter egg
console.log(`
%c   _____ _    _  ___
  / ____| |  | |/ _ \\
 | |    | |__| | (_) |
 | |    |  __  |> _ <
 | |____| |  | | (_) |
  \\_____|_|  |_|\\___/

%c CH8 AGENT - Democratic Distributed AI
%c https://github.com/hudsonrj/ch8-cluster-agent

`, 'color: #00f2ff; font-family: monospace', 'color: #7000ff; font-weight: bold', 'color: #a0aec0');

console.log('%cInterested in the code? Check out our GitHub! 🚀', 'color: #00f2ff; font-size: 14px; font-weight: bold');
