// CH8 Agent Website — script.js

// Navbar scroll effect
window.addEventListener('scroll', () => {
  const nav = document.querySelector('.navbar');
  if (!nav) return;
  nav.style.background = window.scrollY > 40
    ? 'rgba(6,8,16,.97)'
    : 'rgba(6,8,16,.85)';
});

// Smooth reveal on scroll
const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      e.target.style.opacity = '1';
      e.target.style.transform = 'translateY(0)';
    }
  });
}, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' });

const revealSelectors = [
  '.spec-card', '.power-item', '.arch-item', '.sec-layer',
  '.ops-step', '.ops-stat', '.flow-step', '.tool-group', '.cost-item'
];
document.querySelectorAll(revealSelectors.join(',')).forEach((el, i) => {
  el.style.cssText += `opacity:0;transform:translateY(20px);transition:opacity .5s ${i*0.04}s ease,transform .5s ${i*0.04}s ease`;
  revealObserver.observe(el);
});

// Animate stat counters
function animateCounter(el, target, duration) {
  const start = Date.now();
  const tick = () => {
    const p = Math.min((Date.now() - start) / duration, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = Math.round(target * eased);
    if (p < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

const statsEl = document.querySelector('.hero-stats');
if (statsEl) {
  new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (!e.isIntersecting) return;
      e.target.querySelectorAll('.stat-num').forEach(el => {
        const raw = el.textContent;
        const num = parseFloat(raw.replace(/[^\d.]/g, ''));
        const suffix = raw.replace(/[\d.]/g, '');
        if (!num) return;
        el.innerHTML = `<span>${num}</span>${suffix ? `<span style="font-size:.6em;color:var(--blue)">${suffix}</span>` : ''}`;
        animateCounter(el.querySelector('span'), num, 1400);
      });
      e.target.__counted = true;
    });
  }, { threshold: 0.5 }).observe(statsEl);
}

// Click-to-copy code blocks
document.querySelectorAll('pre').forEach(pre => {
  pre.style.cursor = 'pointer';
  pre.title = 'Click to copy';
  pre.addEventListener('click', () => {
    navigator.clipboard.writeText(pre.textContent.trim()).then(() => {
      pre.style.outline = '1px solid #00d4aa';
      setTimeout(() => { pre.style.outline = ''; }, 700);
    });
  });
});
