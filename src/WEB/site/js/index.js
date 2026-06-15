/* ══════════════════════════════════════════════════
   index.js — Page d'accueil Orion
══════════════════════════════════════════════════ */

'use strict';

/* ── API ── */
const API = '/api';

async function sql(q, p = []) {
    try {
        const r = await fetch(`${API}/sql`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sql: q, params: p }),
        });
        const d = await r.json();
        if (!d.success) throw new Error(d.error);
        return d.rows ?? [];
    } catch { return []; }
}

/* ── Normalisation booléens PostgreSQL ── */
const pgBool = v => v === true || v === 1 || v === 't' || String(v) === 'true';

/* ── Échappement HTML ── */
function esc(s) {
    return String(s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/* ════════════════════════════════════
   Horloge UTC (barre d'activité)
════════════════════════════════════ */
function updateClock() {
    const el = document.getElementById('sys-time');
    if (!el) return;
    const now = new Date();
    const hh  = String(now.getUTCHours()).padStart(2, '0');
    const mm  = String(now.getUTCMinutes()).padStart(2, '0');
    const ss  = String(now.getUTCSeconds()).padStart(2, '0');
    el.textContent = `${hh}:${mm}:${ss} UTC`;
}
updateClock();
setInterval(updateClock, 1000);

/* ════════════════════════════════════
   Animation de compteur
════════════════════════════════════ */
function animateCount(el, target, duration = 700) {
    const start = performance.now();
    (function step(now) {
        const t = Math.min((now - start) / duration, 1);
        el.textContent = Math.round(t * target).toLocaleString('fr-FR');
        if (t < 1) requestAnimationFrame(step);
        else el.textContent = target.toLocaleString('fr-FR');
    })(performance.now());
}

function setStat(id, val) {
    const card = document.getElementById(id);
    if (!card) return;
    card.classList.remove('loading');
    const valEl = card.querySelector('.stat-val');
    if (valEl) animateCount(valEl, val);
}

/* ════════════════════════════════════
   Stats live
════════════════════════════════════ */
async function loadStats() {
    const [devRows, onlineRows, offlineRows, linkRows, mapRows, scanProfRows] =
        await Promise.all([
            sql(`SELECT COUNT(*)::int AS n FROM devices`),
            sql(`SELECT COUNT(*)::int AS n FROM device_status WHERE icmp_status = 'Reachable'`),
            sql(`SELECT COUNT(*)::int AS n FROM device_status WHERE icmp_status = 'Unreachable'`),
            sql(`SELECT COUNT(*)::int AS n FROM network_links`),
            sql(`SELECT COUNT(*)::int AS n FROM maps`),
            sql(`SELECT COUNT(*)::int AS n FROM scan_profiles WHERE is_enabled = TRUE`),
        ]);

    setStat('stat-devices', devRows[0]?.n     ?? 0);
    setStat('stat-online',  onlineRows[0]?.n  ?? 0);
    setStat('stat-offline', offlineRows[0]?.n ?? 0);
    setStat('stat-links',   linkRows[0]?.n    ?? 0);
    setStat('stat-maps',    mapRows[0]?.n     ?? 0);

    const maps     = mapRows[0]?.n     ?? 0;
    const devices  = devRows[0]?.n     ?? 0;
    const scanProfs = scanProfRows[0]?.n ?? 0;

    const cm = document.getElementById('count-maps');
    const cd = document.getElementById('count-devices');
    const cs = document.getElementById('count-scan-profiles');
    if (cm) cm.textContent = `${maps} carte${maps !== 1 ? 's' : ''}`;
    if (cd) cd.textContent = `${devices} équipement${devices !== 1 ? 's' : ''}`;
    if (cs) cs.textContent = `${scanProfs} profil${scanProfs !== 1 ? 's' : ''} actif${scanProfs !== 1 ? 's' : ''}`;
}

/* ════════════════════════════════════
   Panel — Réseaux
════════════════════════════════════ */
const STATUS_COLOR = {
    completed: '#16a34a',
    failed:    '#dc2626',
    running:   '#d97706',
    idle:      '#008080',
};

async function loadNetworksPanel() {
    const el = document.getElementById('panel-networks');
    if (!el) return;

    const rows = await sql(`
        SELECT sn.subnet::text     AS subnet,
               sn.last_scan_status AS status,
               sn.last_hosts_found AS hosts,
               ap.name             AS auth
        FROM scan_networks sn
        JOIN auth_profiles ap ON sn.auth_profile_id = ap.id
        ORDER BY sn.last_scan_at DESC NULLS LAST
        LIMIT 8
    `);

    if (!rows.length) {
        el.innerHTML = '<div class="panel-empty">Aucun réseau configuré</div>';
        return;
    }

    el.innerHTML = rows.map(r => {
        const status = r.status || 'idle';
        const color  = STATUS_COLOR[status] || '#5a7070';
        const hosts  = r.hosts ? `${r.hosts} hôtes` : 'Jamais scanné';
        return `
        <div class="scan-row">
            <div class="scan-row-dot" style="background:${color}"></div>
            <div class="scan-row-info">
                <div class="scan-row-name">${esc(r.subnet)}</div>
                <div class="scan-row-meta">${esc(r.auth)} · ${hosts}</div>
            </div>
            <span class="scan-row-badge ${status}">${status}</span>
        </div>`;
    }).join('');
}

/* ════════════════════════════════════
   Panel — Profils de scan
════════════════════════════════════ */
async function loadProfilesPanel() {
    const el = document.getElementById('panel-profiles');
    if (!el) return;

    const rows = await sql(`
        SELECT name, type, is_enabled, concurrency_threads, timeout_ms
        FROM scan_profiles
        ORDER BY is_enabled DESC, name
        LIMIT 8
    `);

    if (!rows.length) {
        el.innerHTML = '<div class="panel-empty">Aucun profil de scan</div>';
        return;
    }

    el.innerHTML = rows.map(r => {
        const on   = pgBool(r.is_enabled);
        const color = on ? '#16a34a' : '#9ca3af';
        const meta = `${r.type} · ${r.timeout_ms} ms · ${r.concurrency_threads} threads`;
        return `
        <div class="scan-row">
            <div class="scan-row-dot" style="background:${color}"></div>
            <div class="scan-row-info">
                <div class="scan-row-name">${esc(r.name)}</div>
                <div class="scan-row-meta">${meta}</div>
            </div>
            <span class="scan-row-badge ${on ? 'completed' : 'idle'}">${on ? 'Actif' : 'Inactif'}</span>
        </div>`;
    }).join('');
}

/* ════════════════════════════════════
   Scroll reveal
════════════════════════════════════ */
const observer = new IntersectionObserver((entries) => {
    entries.forEach(e => {
        if (e.isIntersecting) {
            e.target.classList.add('visible');
            observer.unobserve(e.target);
        }
    });
}, { threshold: 0.12 });

document.querySelectorAll('.reveal').forEach(el => observer.observe(el));

/* ════════════════════════════════════
   Boot
════════════════════════════════════ */
loadStats();
loadNetworksPanel();
loadProfilesPanel();