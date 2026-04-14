/* TPRM AI — Shared client-side utilities */

/**
 * Show a Bootstrap toast notification.
 * @param {string} message
 * @param {string} type  - 'success' | 'danger' | 'warning' | 'info'
 */
function showToast(message, type = 'info') {
    const container = document.getElementById('flash-container');
    if (!container) return;
    const wrapper = document.createElement('div');
    wrapper.className = `alert alert-${type} alert-dismissible fade show`;
    wrapper.role = 'alert';
    wrapper.innerHTML = `${message}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>`;
    container.prepend(wrapper);
    setTimeout(() => {
        wrapper.classList.remove('show');
        setTimeout(() => wrapper.remove(), 300);
    }, 6000);
}

/**
 * Update an upload zone to show selected file name(s).
 */
function updateUploadZone(input) {
    const zone = input.closest('.upload-zone');
    if (!zone) return;
    const files = input.files;
    if (files.length === 0) {
        zone.classList.remove('has-files');
        return;
    }
    zone.classList.add('has-files');
    const p = zone.querySelector('p');
    if (p) {
        if (files.length === 1) {
            p.textContent = files[0].name;
        } else {
            p.textContent = files.length + ' file(s) selected';
        }
    }
    const icon = zone.querySelector('i');
    if (icon) icon.className = 'bi bi-check-circle-fill text-success';
}

// ── Global Background Assessment Poller ─────────────────────────────
//
// Tracks running assessments across all pages via localStorage.
// Key: tprm_running  Value: JSON object { id: {vendorName, startedAt} }
//
(function () {
    const STORAGE_KEY = 'tprm_running';
    const POLL_MS = 5000;

    function getRunning() {
        try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); }
        catch { return {}; }
    }
    function setRunning(obj) {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(obj));
    }

    // Called by the assessment detail page when a pipeline starts
    window.tprmTrackAssessment = function (id, vendorName) {
        const running = getRunning();
        running[id] = { vendorName, startedAt: Date.now() };
        setRunning(running);
        updateRunningBadge();
    };

    // Called when user navigates away from the running card
    window.tprmMinimizeAssessment = function (id, vendorName) {
        window.tprmTrackAssessment(id, vendorName);
        window.location.href = '/';
    };

    function updateRunningBadge() {
        const running = getRunning();
        const count = Object.keys(running).length;
        const badge  = document.getElementById('global-running-badge');
        const pill   = document.getElementById('global-running-pill');
        if (!badge || !pill) return;
        if (count > 0) {
            badge.textContent = count;
            pill.style.display = '';
        } else {
            pill.style.display = 'none';
        }
    }

    function fireBrowserNotification(vendorName, status, id) {
        if (!('Notification' in window)) return;
        const title = status === 'completed'
            ? `\u2705 Assessment Complete: ${vendorName}`
            : `\u274C Assessment Failed: ${vendorName}`;
        const body = status === 'completed'
            ? 'Risk analysis finished. Click to view the report.'
            : 'The pipeline encountered an error. Click to see details.';
        const show = () => {
            const n = new Notification(title, { body, icon: '/static/img/favicon.png', tag: id });
            n.onclick = () => { window.focus(); window.location.href = `/assessments/${id}`; };
        };
        if (Notification.permission === 'granted') {
            show();
        } else if (Notification.permission !== 'denied') {
            Notification.requestPermission().then(p => { if (p === 'granted') show(); });
        }
    }

    async function pollAll() {
        const running = getRunning();
        const ids = Object.keys(running);
        if (!ids.length) return;

        await Promise.all(ids.map(async (id) => {
            try {
                const resp = await fetch(`/api/assessments/${id}/status`, { credentials: 'same-origin' });
                if (!resp.ok) return;
                const data = await resp.json();

                // Update in-page progress if the detail card is visible
                const runBar   = document.getElementById('run-bar');
                const runLabel = document.getElementById('run-label');
                if (runBar && runLabel && data.current_step !== undefined) {
                    const pct = Math.round((data.current_step / data.total_steps) * 100);
                    runBar.style.width = pct + '%';
                    runBar.textContent = pct + '%';
                    runLabel.textContent = data.step_message || 'Processing...';
                    document.querySelectorAll('#run-steps .step-tracker').forEach(el => {
                        const s = parseInt(el.dataset.step);
                        const icon = el.querySelector('i');
                        if (!icon) return;
                        if (s < data.current_step) icon.className = 'bi bi-check-circle-fill text-success';
                        else if (s === data.current_step) icon.className = 'bi bi-arrow-right-circle-fill text-primary';
                    });
                }

                if (data.status === 'completed' || data.status === 'failed') {
                    const info = running[id];
                    const vendorName = info ? info.vendorName : 'Assessment';

                    // Remove from tracking
                    const updated = getRunning();
                    delete updated[id];
                    setRunning(updated);
                    updateRunningBadge();

                    // Toast notification (visible on any page)
                    const safeVendor = vendorName.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
                    if (data.status === 'completed') {
                        showToast(
                            `<i class="bi bi-check-circle-fill me-2"></i><strong>${safeVendor}</strong> assessment complete. 
                            <a href="/assessments/${id}" class="alert-link ms-2">View Report &rarr;</a>`,
                            'success'
                        );
                    } else {
                        showToast(
                            `<i class="bi bi-x-circle-fill me-2"></i><strong>${safeVendor}</strong> assessment failed. 
                            <a href="/assessments/${id}" class="alert-link ms-2">View Details &rarr;</a>`,
                            'danger'
                        );
                    }

                    // Browser notification
                    fireBrowserNotification(vendorName, data.status, id);

                    // If currently on that assessment's detail page, reload to show results
                    if (window.location.pathname === `/assessments/${id}`) {
                        setTimeout(() => location.reload(), 800);
                    }
                }
            } catch (e) { /* network blip — silently ignore */ }
        }));
    }

    // Start polling
    updateRunningBadge();

    // On every page load, reconcile localStorage with the server's current state.
    // Adds any server-running assessments not yet tracked, and removes stale
    // localStorage entries whose assessments are no longer running.
    (async function hydrateRunning() {
        try {
            const resp = await fetch('/api/assessments', { credentials: 'same-origin' });
            if (!resp.ok) return;
            const payload = await resp.json();
            const all = Array.isArray(payload) ? payload : (payload.assessments || []);
            const serverRunningIds = new Set(all.filter(a => a.status === 'running').map(a => a.id));

            const tracked = getRunning();
            let changed = false;

            // Add newly-running assessments not yet in localStorage
            serverRunningIds.forEach(id => {
                if (!tracked[id]) {
                    const a = all.find(x => x.id === id);
                    tracked[id] = { vendorName: a.vendor_name, startedAt: Date.now() };
                    changed = true;
                }
            });

            // Remove stale localStorage entries that the server no longer reports as running
            Object.keys(tracked).forEach(id => {
                if (!serverRunningIds.has(id)) {
                    delete tracked[id];
                    changed = true;
                }
            });

            if (changed) { setRunning(tracked); updateRunningBadge(); }
        } catch (_) { /* network blip */ }
    })();

    setInterval(pollAll, POLL_MS);
    pollAll(); // immediate first check
})();

