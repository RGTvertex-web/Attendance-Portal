(function() {
    // Respect user preference for reduced motion
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (prefersReducedMotion.matches) return;

    const canvas = document.getElementById('network-bg');
    if (!canvas) return;

    const ctx = canvas.getContext('2d', { alpha: true });
    
    // Configuration
    const NODE_COUNT = window.innerWidth > 768 ? 60 : 30; // Fewer nodes on mobile
    const MAX_DISTANCE = 150;
    const NODE_RADIUS = 2;
    const SPEED = 0.5;
    const COLOR = 'rgba(156, 163, 175, 0.4)'; // matches --color-text-muted with opacity
    
    let nodes = [];
    let animationFrameId;
    let isVisible = true;
    
    // Resize handler
    function resize() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }
    
    window.addEventListener('resize', resize);
    resize();

    // Node class
    class Node {
        constructor() {
            this.x = Math.random() * canvas.width;
            this.y = Math.random() * canvas.height;
            this.vx = (Math.random() - 0.5) * SPEED;
            this.vy = (Math.random() - 0.5) * SPEED;
        }

        update() {
            this.x += this.vx;
            this.y += this.vy;

            // Bounce off edges
            if (this.x < 0 || this.x > canvas.width) this.vx *= -1;
            if (this.y < 0 || this.y > canvas.height) this.vy *= -1;
        }

        draw() {
            ctx.beginPath();
            ctx.arc(this.x, this.y, NODE_RADIUS, 0, Math.PI * 2);
            ctx.fillStyle = COLOR;
            ctx.fill();
        }
    }

    // Initialize nodes
    for (let i = 0; i < NODE_COUNT; i++) {
        nodes.push(new Node());
    }

    // Draw lines between nearby nodes
    function drawLines() {
        for (let i = 0; i < nodes.length; i++) {
            for (let j = i + 1; j < nodes.length; j++) {
                const dx = nodes[i].x - nodes[j].x;
                const dy = nodes[i].y - nodes[j].y;
                const distance = Math.sqrt(dx * dx + dy * dy);

                if (distance < MAX_DISTANCE) {
                    const opacity = 1 - (distance / MAX_DISTANCE);
                    ctx.beginPath();
                    ctx.moveTo(nodes[i].x, nodes[i].y);
                    ctx.lineTo(nodes[j].x, nodes[j].y);
                    ctx.strokeStyle = `rgba(156, 163, 175, ${opacity * 0.3})`;
                    ctx.lineWidth = 1;
                    ctx.stroke();
                }
            }
        }
    }

    // Main animation loop
    function animate() {
        if (!isVisible) return; // Pause if tab is inactive
        
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        nodes.forEach(node => {
            node.update();
            node.draw();
        });
        
        drawLines();
        
        animationFrameId = requestAnimationFrame(animate);
    }

    // Visibility API for performance
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            isVisible = false;
            cancelAnimationFrame(animationFrameId);
        } else {
            isVisible = true;
            animate();
        }
    });

    // Start animation
    animate();
})();
