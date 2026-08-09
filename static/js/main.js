/* ============================================
   PRESENTATION EVALUATION PORTAL - MAIN JS
   ============================================ */

document.addEventListener('DOMContentLoaded', function() {
    initLoader();
    initAOS();
    initTheme();
    initSidebar();
    initDropdowns();
    initCounters();
    initNotifications();
    initPasswordToggles();
});

/* Loading Screen */
function initLoader() {
    const loader = document.getElementById('page-loader');
    if (!loader) return;
    window.addEventListener('load', () => {
        setTimeout(() => loader.classList.add('hidden'), 600);
    });
    setTimeout(() => loader.classList.add('hidden'), 1500);
}

/* AOS Animation */
function initAOS() {
    if (typeof AOS !== 'undefined') {
        AOS.init({
            duration: 600,
            once: true,
            offset: 50,
            easing: 'ease-out-cubic'
        });
    }
}

/* Dark / Light Theme */
function initTheme() {
    const html = document.documentElement;
    const saved = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

    if (saved) {
        html.setAttribute('data-bs-theme', saved);
    } else if (prefersDark) {
        html.setAttribute('data-bs-theme', 'dark');
    }

    updateAllThemeIcons();

    // App theme toggle
    const appToggle = document.getElementById('themeToggle');
    if (appToggle) {
        appToggle.addEventListener('click', () => {
            toggleTheme();
        });
    }

    // Public theme toggle (landing page & auth)
    const publicToggle = document.getElementById('themeTogglePublic');
    if (publicToggle) {
        publicToggle.addEventListener('click', () => {
            toggleTheme();
        });
    }

    // Settings page toggle sync
    const settingsToggle = document.getElementById('darkModeToggle');
    if (settingsToggle) {
        settingsToggle.checked = html.getAttribute('data-bs-theme') === 'dark';
        settingsToggle.addEventListener('change', (e) => {
            const next = e.target.checked ? 'dark' : 'light';
            html.setAttribute('data-bs-theme', next);
            localStorage.setItem('theme', next);
            updateAllThemeIcons();
        });
    }
}

function toggleTheme() {
    const html = document.documentElement;
    const current = html.getAttribute('data-bs-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-bs-theme', next);
    localStorage.setItem('theme', next);
    updateAllThemeIcons();
}

function updateAllThemeIcons() {
    const isDark = document.documentElement.getAttribute('data-bs-theme') === 'dark';
    const iconHtml = isDark ? '<i class="fas fa-sun"></i>' : '<i class="fas fa-moon"></i>';

    document.querySelectorAll('#themeToggle, #themeTogglePublic').forEach(btn => {
        if (btn) btn.innerHTML = iconHtml;
    });
}

/* Sidebar Mobile */
function initSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    const openBtn = document.getElementById('sidebarToggle');
    const closeBtn = document.getElementById('sidebarClose');

    function open() {
        sidebar?.classList.add('show');
        overlay?.classList.add('show');
    }
    function close() {
        sidebar?.classList.remove('show');
        overlay?.classList.remove('show');
    }

    openBtn?.addEventListener('click', open);
    closeBtn?.addEventListener('click', close);
    overlay?.addEventListener('click', close);
}

/* Sidebar Dropdowns */
function initDropdowns() {
    document.querySelectorAll('.nav-dropdown-toggle').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const parent = btn.closest('.nav-dropdown');
            parent.classList.toggle('open');
        });
    });
}

/* Animated Counters */
function initCounters() {
    const counters = document.querySelectorAll('[data-counter]');
    if (!counters.length) return;

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const el = entry.target;
                const target = parseFloat(el.getAttribute('data-counter'));
                const isFloat = target % 1 !== 0;
                const duration = 1500;
                const start = performance.now();

                function update(now) {
                    const elapsed = now - start;
                    const progress = Math.min(elapsed / duration, 1);
                    const ease = 1 - Math.pow(1 - progress, 3);
                    const current = target * ease;
                    el.textContent = isFloat ? current.toFixed(1) : Math.floor(current);
                    if (progress < 1) requestAnimationFrame(update);
                }
                requestAnimationFrame(update);
                observer.unobserve(el);
            }
        });
    }, { threshold: 0.5 });

    counters.forEach(c => observer.observe(c));
}

/* Toast Notifications */
function showToast(message, type) {
    type = type || 'info';
    const container = document.getElementById('toast-container');
    if (!container) return;

    const icons = {
        success: 'fa-check-circle',
        error: 'fa-times-circle',
        warning: 'fa-exclamation-triangle',
        info: 'fa-info-circle'
    };

    const toast = document.createElement('div');
    toast.className = 'custom-toast';
    toast.innerHTML = `
        <div class="toast-icon ${type}">
            <i class="fas ${icons[type] || icons.info}"></i>
        </div>
        <div class="toast-content">
            <div class="toast-title">${type.charAt(0).toUpperCase() + type.slice(1)}</div>
            <div class="toast-message">${escapeHtml(message)}</div>
        </div>
        <button class="toast-close" onclick="this.parentElement.remove()">
            <i class="fas fa-times"></i>
        </button>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => toast.remove(), 400);
    }, 5000);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/* Notifications Fetch */
function initNotifications() {
    const badge = document.getElementById('notifBadge');
    const panel = document.getElementById('notificationPanel');
    const btn = document.getElementById('notificationBtn');
    const list = document.getElementById('notificationList');

    if (!btn) return;

    btn.addEventListener('click', (e) => {
        e.stopPropagation();
        panel?.classList.toggle('show');
    });

    document.addEventListener('click', (e) => {
        if (!panel?.contains(e.target) && e.target !== btn) {
            panel?.classList.remove('show');
        }
    });

    if (typeof currentUserId !== 'undefined') {
        fetch('/api/notifications')
            .then(r => r.json())
            .then(data => {
                if (data.length) {
                    if (badge) {
                        badge.textContent = data.length;
                        badge.style.display = 'flex';
                    }
                    if (list) {
                        list.innerHTML = data.map(n => `
                            <div class="notification-item" data-id="${n.id}">
                                <p>${escapeHtml(n.message)}</p>
                                <span>${n.date}</span>
                            </div>
                        `).join('');
                    }
                }
            })
            .catch(() => {});
    }

    document.querySelector('.mark-all-read')?.addEventListener('click', () => {
        document.querySelectorAll('.notification-item').forEach(item => {
            const id = item.getAttribute('data-id');
            if (id) fetch(`/api/notifications/${id}/read`, { method: 'POST' });
        });
        if (badge) badge.style.display = 'none';
        if (list) list.innerHTML = '<div class="notification-empty">No new notifications</div>';
    });
}

/* Password Toggle */
function initPasswordToggles() {
    window.togglePassword = function(inputId) {
        const input = document.getElementById(inputId);
        if (!input) return;

        const parent = input.closest('.form-floating');
        const btn = parent?.querySelector('.password-toggle');

        const isPassword = input.type === 'password';
        input.type = isPassword ? 'text' : 'password';
        if (btn) btn.innerHTML = `<i class="fas fa-eye${isPassword ? '-slash' : ''}"></i>`;
    };
}

/* Filter helpers */
function filterSemester(name) {
    showToast('Filtering by ' + name + '...', 'info');
}
function filterDepartment(name) {
    showToast('Filtering by ' + name + '...', 'info');
}


/* ============================================================
   PROFILE PICTURE CROPPER
   ============================================================ */

function initProfileCropper() {
    const fileInput = document.getElementById('cropperFileInput');
    const wrapper = document.getElementById('cropperWrapper');
    const controls = document.getElementById('cropperControls');
    const hint = document.getElementById('cropperHint');
    const img = document.getElementById('cropperImage');
    const zoomSlider = document.getElementById('cropperZoom');
    const saveBtn = document.getElementById('cropperSave');
    const hiddenInput = document.getElementById('hiddenProfilePic');
    const profileForm = document.getElementById('profileForm');

    if (!fileInput || !img) return;

    let state = { scale: 1, tx: 0, ty: 0, dragging: false, startX: 0, startY: 0 };
    let naturalWidth = 0, naturalHeight = 0;

    fileInput.addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = function(evt) {
            img.src = evt.target.result;
            img.onload = function() {
                naturalWidth = img.naturalWidth;
                naturalHeight = img.naturalHeight;
                state.scale = 1;
                state.tx = 0;
                state.ty = 0;
                zoomSlider.value = 1;
                updateTransform();
                wrapper.style.display = 'block';
                controls.style.display = 'block';
                hint.style.display = 'none';
                saveBtn.disabled = false;
            };
        };
        reader.readAsDataURL(file);
    });

    function updateTransform() {
        img.style.transform = 'translate(-50%, -50%) translate(' + state.tx + 'px, ' + state.ty + 'px) scale(' + state.scale + ')';
    }

    zoomSlider.addEventListener('input', function() {
        state.scale = parseFloat(this.value);
        updateTransform();
    });

    img.addEventListener('mousedown', function(e) {
        state.dragging = true;
        state.startX = e.clientX - state.tx;
        state.startY = e.clientY - state.ty;
        img.style.cursor = 'grabbing';
    });

    document.addEventListener('mousemove', function(e) {
        if (!state.dragging) return;
        state.tx = e.clientX - state.startX;
        state.ty = e.clientY - state.startY;
        updateTransform();
    });

    document.addEventListener('mouseup', function() {
        state.dragging = false;
        if (img) img.style.cursor = 'grab';
    });

    // Touch support
    img.addEventListener('touchstart', function(e) {
        if (e.touches.length === 1) {
            state.dragging = true;
            state.startX = e.touches[0].clientX - state.tx;
            state.startY = e.touches[0].clientY - state.ty;
        }
    }, { passive: false });

    document.addEventListener('touchmove', function(e) {
        if (!state.dragging || e.touches.length !== 1) return;
        e.preventDefault();
        state.tx = e.touches[0].clientX - state.startX;
        state.ty = e.touches[0].clientY - state.startY;
        updateTransform();
    }, { passive: false });

    document.addEventListener('touchend', function() {
        state.dragging = false;
    });

    saveBtn.addEventListener('click', function() {
        const viewport = document.getElementById('cropperViewport');
        const vpSize = viewport.offsetWidth;
        const outputSize = 400;

        // Calculate source crop region in intrinsic coordinates
        // Image center is at viewport center + (tx, ty), scaled by scale
        // A point (ix, iy) in intrinsic coords maps to viewport coords:
        // vp_x = vpSize/2 + tx + (ix - naturalWidth/2) * scale
        // We want the region where 0 <= vp_x <= vpSize and 0 <= vp_y <= vpSize

        const ix1 = naturalWidth / 2 + (0 - vpSize / 2 - state.tx) / state.scale;
        const iy1 = naturalHeight / 2 + (0 - vpSize / 2 - state.ty) / state.scale;
        const ix2 = naturalWidth / 2 + (vpSize - vpSize / 2 - state.tx) / state.scale;
        const iy2 = naturalHeight / 2 + (vpSize - vpSize / 2 - state.ty) / state.scale;

        let sx = Math.max(0, Math.min(ix1, ix2));
        let sy = Math.max(0, Math.min(iy1, iy2));
        let sw = Math.min(Math.abs(ix2 - ix1), naturalWidth - sx);
        let sh = Math.min(Math.abs(iy2 - iy1), naturalHeight - sy);

        // Force square crop, centered
        const sq = Math.min(sw, sh);
        const cx = sx + sw / 2;
        const cy = sy + sh / 2;
        const fsx = Math.max(0, cx - sq / 2);
        const fsy = Math.max(0, cy - sq / 2);
        const fsw = Math.min(sq, naturalWidth - fsx);
        const fsh = Math.min(sq, naturalHeight - fsy);

        const canvas = document.createElement('canvas');
        canvas.width = outputSize;
        canvas.height = outputSize;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, fsx, fsy, fsw, fsh, 0, 0, outputSize, outputSize);

        canvas.toBlob(function(blob) {
            const croppedFile = new File([blob], 'profile_picture.png', { type: 'image/png' });
            const dt = new DataTransfer();
            dt.items.add(croppedFile);
            hiddenInput.files = dt.files;

            // Close modal and submit form
            const modalEl = document.getElementById('cropperModal');
            const modal = bootstrap.Modal.getInstance(modalEl);
            if (modal) modal.hide();
            if (profileForm) profileForm.submit();
        }, 'image/png');
    });
}

/* ============================================================
   PASSWORD TOGGLE - Enhanced for admin profile
   ============================================================ */

function togglePassword(el) {
    let input, btn;
    if (typeof el === 'string') {
        input = document.getElementById(el);
        const parent = input.closest('.position-relative') || input.closest('.mb-3');
        btn = parent.querySelector('.password-toggle');
    } else {
        btn = el;
        const parent = btn.closest('.position-relative') || btn.closest('.mb-3');
        input = parent.querySelector('input[type="password"], input[type="text"]');
    }
    if (!input) return;
    const isPassword = input.type === 'password';
    input.type = isPassword ? 'text' : 'password';
    if (btn) btn.innerHTML = '<i class="fas fa-eye' + (isPassword ? '-slash' : '') + '"></i>';
}
