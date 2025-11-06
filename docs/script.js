// Smooth scroll for navigation links
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

// Navbar scroll effect
let lastScroll = 0;
const navbar = document.querySelector('.navbar');

window.addEventListener('scroll', () => {
    const currentScroll = window.pageYOffset;

    if (currentScroll > 100) {
        navbar.style.boxShadow = '0 2px 10px rgba(0, 0, 0, 0.1)';
    } else {
        navbar.style.boxShadow = '0 1px 3px rgba(0, 0, 0, 0.1)';
    }

    lastScroll = currentScroll;
});

// Demo animation functionality
const triggerBtn = document.getElementById('triggerDemo');
const resetBtn = document.getElementById('resetDemo');
const timelineItems = document.querySelectorAll('.timeline-item');

let demoRunning = false;
let currentStep = 0;

// Lambda Function URL - Replace this with actual URL from terraform output after deployment
// Run: terraform output ingestor_demo_url
const LAMBDA_DEMO_URL = 'YOUR_LAMBDA_URL_HERE';

function resetDemo() {
    timelineItems.forEach(item => {
        item.classList.remove('active');
    });
    currentStep = 0;
    demoRunning = false;
    triggerBtn.disabled = false;
    triggerBtn.textContent = 'Trigger Demo Alert';
}

async function runDemo() {
    if (demoRunning) return;

    demoRunning = true;
    triggerBtn.disabled = true;
    triggerBtn.textContent = 'Triggering Real Alert...';

    // Reset first
    resetDemo();
    demoRunning = true;
    triggerBtn.disabled = true;
    triggerBtn.textContent = 'Triggering Real Alert...';

    try {
        // Check if Lambda URL is configured
        if (LAMBDA_DEMO_URL === 'YOUR_LAMBDA_URL_HERE') {
            console.warn('Lambda URL not configured - running animation only');
            triggerBtn.textContent = 'Demo Running (Simulated)...';
        } else {
            // Actually trigger the Lambda function
            console.log('Triggering Lambda function:', LAMBDA_DEMO_URL);

            const response = await fetch(LAMBDA_DEMO_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: 'Demo Alert: Database connection timeout after 30 seconds',
                    severity: 'HIGH',
                    source: 'demo-web-page',
                    log_group: '/aws/lambda/demo-app',
                    log_stream: 'demo-stream'
                })
            });

            if (response.ok) {
                const result = await response.json();
                console.log('✅ Alert triggered successfully:', result);
                triggerBtn.textContent = '✅ Real Alert Sent!';
            } else {
                console.error('❌ Failed to trigger alert:', response.status);
                triggerBtn.textContent = '❌ Failed - Running Simulation';
            }
        }

        // Activate steps sequentially to show the process
        const delays = [500, 2500, 5000, 7500];

        timelineItems.forEach((item, index) => {
            setTimeout(() => {
                item.classList.add('active');
                currentStep = index + 1;

                // Add some visual feedback
                item.scrollIntoView({ behavior: 'smooth', block: 'center' });

                // When demo completes
                if (index === timelineItems.length - 1) {
                    setTimeout(() => {
                        demoRunning = false;
                        triggerBtn.disabled = false;
                        triggerBtn.textContent = 'Trigger Demo Alert';
                    }, 1000);
                }
            }, delays[index]);
        });

    } catch (error) {
        console.error('Error triggering demo:', error);
        triggerBtn.textContent = '❌ Error - See Console';

        // Still run animation
        const delays = [500, 2500, 5000, 7500];
        timelineItems.forEach((item, index) => {
            setTimeout(() => {
                item.classList.add('active');
                currentStep = index + 1;
                item.scrollIntoView({ behavior: 'smooth', block: 'center' });

                if (index === timelineItems.length - 1) {
                    setTimeout(() => {
                        demoRunning = false;
                        triggerBtn.disabled = false;
                        triggerBtn.textContent = 'Trigger Demo Alert';
                    }, 1000);
                }
            }, delays[index]);
        });
    }
}

triggerBtn.addEventListener('click', runDemo);
resetBtn.addEventListener('click', resetDemo);

// Intersection Observer for scroll animations
const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -100px 0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.style.opacity = '1';
            entry.target.style.transform = 'translateY(0)';
        }
    });
}, observerOptions);

// Animate feature cards on scroll
document.querySelectorAll('.feature-card').forEach((card, index) => {
    card.style.opacity = '0';
    card.style.transform = 'translateY(30px)';
    card.style.transition = `all 0.6s ease ${index * 0.1}s`;
    observer.observe(card);
});

// Animate pipeline stages on scroll
document.querySelectorAll('.pipeline-stage').forEach((stage, index) => {
    stage.style.opacity = '0';
    stage.style.transform = 'translateY(30px)';
    stage.style.transition = `all 0.6s ease ${index * 0.15}s`;
    observer.observe(stage);
});

// Add particle effect to hero section (subtle) - Catppuccin colors
function createParticle() {
    const hero = document.querySelector('.hero');
    const particle = document.createElement('div');

    // Randomly choose between mauve, pink, and sapphire
    const colors = [
        'rgba(203, 166, 247, 0.4)', // mauve
        'rgba(245, 194, 231, 0.4)', // pink
        'rgba(116, 199, 236, 0.4)'  // sapphire
    ];
    const randomColor = colors[Math.floor(Math.random() * colors.length)];

    particle.style.position = 'absolute';
    particle.style.width = '4px';
    particle.style.height = '4px';
    particle.style.background = randomColor;
    particle.style.borderRadius = '50%';
    particle.style.left = Math.random() * 100 + '%';
    particle.style.top = '100%';
    particle.style.pointerEvents = 'none';
    particle.style.animation = 'float-up 8s linear infinite';

    hero.appendChild(particle);

    setTimeout(() => {
        particle.remove();
    }, 8000);
}

// Create particles periodically
setInterval(createParticle, 2000);

// Add CSS for particle animation
const style = document.createElement('style');
style.textContent = `
    @keyframes float-up {
        0% {
            transform: translateY(0) scale(1);
            opacity: 0;
        }
        10% {
            opacity: 0.5;
        }
        90% {
            opacity: 0.5;
        }
        100% {
            transform: translateY(-100vh) scale(0.5);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

// Copy code functionality (if we add code snippets later)
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        // Show feedback
        console.log('Copied to clipboard');
    });
}

// Add hover effects to architecture boxes - Catppuccin colors
document.querySelectorAll('.arch-box').forEach(box => {
    box.addEventListener('mouseenter', () => {
        box.style.transform = 'scale(1.05)';
        box.style.boxShadow = '0 4px 20px rgba(203, 166, 247, 0.4)';
    });

    box.addEventListener('mouseleave', () => {
        box.style.transform = 'scale(1)';
        box.style.boxShadow = 'none';
    });
});

// Stats counter animation
function animateCounter(element, target) {
    const duration = 2000;
    const start = 0;
    const increment = target / (duration / 16);
    let current = start;

    const timer = setInterval(() => {
        current += increment;
        if (current >= target) {
            element.textContent = target;
            clearInterval(timer);
        } else {
            element.textContent = Math.floor(current);
        }
    }, 16);
}

// Trigger counter animation when stats come into view
const statsObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            const statNumber = entry.target.querySelector('.stat-number');
            const text = statNumber.textContent;

            // Only animate if it's a number
            if (text.match(/^\d+$/)) {
                animateCounter(statNumber, parseInt(text));
            }

            statsObserver.unobserve(entry.target);
        }
    });
}, { threshold: 0.5 });

document.querySelectorAll('.stat').forEach(stat => {
    statsObserver.observe(stat);
});

// Add typing effect to hero title (optional - can be enabled)
function typeWriter(element, text, speed = 50) {
    let i = 0;
    element.textContent = '';

    function type() {
        if (i < text.length) {
            element.textContent += text.charAt(i);
            i++;
            setTimeout(type, speed);
        }
    }

    type();
}

// Mobile menu toggle (if we add hamburger menu)
function createMobileMenu() {
    const navLinks = document.querySelector('.nav-links');
    const burger = document.createElement('div');
    burger.classList.add('burger');
    burger.innerHTML = '<span></span><span></span><span></span>';

    // Add burger to nav
    const navContent = document.querySelector('.nav-content');
    navContent.appendChild(burger);

    burger.addEventListener('click', () => {
        navLinks.classList.toggle('active');
        burger.classList.toggle('active');
    });
}

// Check if mobile and create menu
if (window.innerWidth <= 768) {
    // Mobile menu can be added here if needed
    console.log('Mobile view detected');
}

// Log when page is loaded
console.log('MCP First-Responder landing page loaded');
console.log('Demo ready - click "Trigger Demo Alert" to see it in action');