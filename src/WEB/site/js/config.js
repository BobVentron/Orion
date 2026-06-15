'use strict';

/* ══════════════════════════════════════════════════════════
   config.js — Page Paramétrage
   Orion · DuckInc
══════════════════════════════════════════════════════════ */

const API_BASE = '/api';

async function sql(query, params = []) {
    const res = await fetch(`${API_BASE}/sql`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sql: query, params }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error || 'Erreur SQL inconnue');
    return data.rows ?? [];
}

async function exec(query, params = []) {
    const res = await fetch(`${API_BASE}/sql`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sql: query, params }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error || 'Erreur SQL inconnue');
    return { rowCount: data.rowCount ?? 0, rows: data.rows ?? [] };
}

/* ── Normalisation des booléens PostgreSQL ────────────────────────────────
   Le driver peut retourner : true / false / 1 / 0 / "t" / "f" / "true" / "false"  */
function pgBool(v) {
    return v === true || v === 1 || v === 't' || String(v).toLowerCase() === 'true';
}


/* ════════════════════════════════════════════════════════
   UI — SOUS-NAVBAR
════════════════════════════════════════════════════════ */
document.querySelectorAll('.sub-nav-btn').forEach(btn => {
    btn.addEventListener('click', function () {
        document.querySelectorAll('.sub-nav-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.config-tab').forEach(t => t.classList.remove('active'));
        this.classList.add('active');
        const t = document.getElementById('tab-' + this.dataset.tab);
        if (t) t.classList.add('active');
    });
});


/* ════════════════════════════════════════════════════════
   UI — MODALS
════════════════════════════════════════════════════════ */
function openModal(id) { const m = document.getElementById(id); if (m) m.style.display = 'flex'; }
function closeModal(id) { const m = document.getElementById(id); if (m) m.style.display = 'none'; }
window.addEventListener('click', e => {
    document.querySelectorAll('.modal').forEach(m => { if (e.target === m) m.style.display = 'none'; });
});
window.addEventListener('keydown', e => {
    if (e.key === 'Escape') document.querySelectorAll('.modal').forEach(m => m.style.display = 'none');
});


/* ════════════════════════════════════════════════════════
   UI — HELPERS
════════════════════════════════════════════════════════ */
function cardLoading(id) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = '<div class="card-loading">🦆 Chargement…</div>';
}
function cardError(id, msg) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = `<div class="card-error">⚠️ ${msg}</div>`;
}
function cardEmpty(id, msg) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = `<div class="card-empty">${msg}</div>`;
}

function bpsHuman(bps) {
    if (!bps) return '0 bps';
    if (bps >= 1e12) return (bps / 1e12).toFixed(0) + ' Tbps';
    if (bps >= 1e9)  return (bps / 1e9).toFixed(0)  + ' Gbps';
    if (bps >= 1e6)  return (bps / 1e6).toFixed(0)  + ' Mbps';
    if (bps >= 1e3)  return (bps / 1e3).toFixed(0)  + ' Kbps';
    return bps + ' bps';
}

/* Formatage identique à la CLI (cmd_network_status) */
function fmtInterval(s) {
    s = parseInt(s);
    if (!s || s === 0) return 'Scan unique';
    if (s < 60)        return `${s}s`;
    if (s < 3600)      return `${Math.round(s / 60)} min`;
    return `${Math.round(s / 3600)} h`;
}

function dashLabel(d) {
    if (!d)                          return 'Trait plein';
    if (d === '5,5' || d === '6,4') return 'Pointillés';
    return 'Tirets-points';
}
function dashSvg(color, dash) {
    const da = dash ? ` stroke-dasharray="${dash}"` : '';
    return `<svg width="72" height="14" style="display:block"><line x1="4" y1="7" x2="68" y2="7" stroke="${color}" stroke-width="3" stroke-linecap="round"${da}/></svg>`;
}
function thickSvg(px, color = '#008080') {
    const h = Math.max(px + 10, 20);
    return `<svg width="80" height="${h}" style="display:block"><line x1="6" y1="${h/2}" x2="74" y2="${h/2}" stroke="${color}" stroke-width="${px}" stroke-linecap="round"/></svg>`;
}

function populateSelect(id, rows, labelFn, emptyLabel = '— Choisir —') {
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = `<option value="">${emptyLabel}</option>`
        + rows.map(r => `<option value="${r.id}">${labelFn(r)}</option>`).join('');
}

const SOURCE_BADGE = { Local: 'badge-teal', LDAP: 'badge-purple', SAML: 'badge-yellow', API_Token: 'badge-gray' };
const SCAN_STATUS  = { completed: 'badge-green', failed: 'badge-red', running: 'badge-yellow', idle: 'badge-gray' };
const DASH_CYCLE   = [null, '5,5', '10,3,3,3'];
const _cache       = { linkColors: [], mapStatus: [] };


/* ════════════════════════════════════════════════════════
   SNMP — toggle v2c / v3
════════════════════════════════════════════════════════ */
function toggleSnmpV3() {
    const v = document.getElementById('snmp-version')?.value;
    document.getElementById('snmp-v2-block').style.display = v === 'v3' ? 'none' : 'block';
    document.getElementById('snmp-v3-block').style.display = v === 'v3' ? 'block' : 'none';
}

function updateThicknessPreview(val) {
    const line  = document.getElementById('preview-line');
    const label = document.getElementById('thickness-val');
    if (line)  line.setAttribute('stroke-width', val);
    if (label) label.textContent = val + ' px';
}


/* ════════════════════════════════════════════════════════
   ██  SNMP — auth_snmp
   Champs : name, version, port, community (v1/v2c)
            v3_user, v3_level, v3_auth_proto, v3_auth_pass,
            v3_priv_proto, v3_priv_pass (v3)
════════════════════════════════════════════════════════ */
async function loadSnmp() {
    cardLoading('snmp-list');
    try {
        const rows = await sql(`
            SELECT id, name, version, port,
                   community, v3_user, v3_level, v3_auth_proto, v3_priv_proto
            FROM auth_snmp ORDER BY name
        `);
        if (!rows.length) { cardEmpty('snmp-list', 'Aucun profil SNMP configuré.'); return; }
        document.getElementById('snmp-list').innerHTML = rows.map(s => `
            <div class="config-card">
                <div class="card-info">
                    <div class="card-name">
                        ${s.name}
                        <span class="badge badge-teal">${s.version}</span>
                    </div>
                    <div class="card-meta">
                        <span>Port : <strong>${s.port}</strong></span>
                        ${s.community     ? `<span>Community : <code>${s.community}</code></span>` : ''}
                        ${s.v3_user       ? `<span>User : <strong>${s.v3_user}</strong></span>` : ''}
                        ${s.v3_level      ? `<span>${s.v3_level}</span>` : ''}
                        ${s.v3_auth_proto ? `<span>Auth : ${s.v3_auth_proto}</span>` : ''}
                        ${s.v3_priv_proto ? `<span>Priv : ${s.v3_priv_proto}</span>` : ''}
                    </div>
                </div>
                <div class="card-actions">
                    <button class="btn-icon btn-icon-danger" onclick="deleteSnmp(${s.id}, '${s.name.replace(/'/g, "\\'")}')">🗑</button>
                </div>
            </div>`).join('');
    } catch (e) { cardError('snmp-list', e.message); }
}

async function deleteSnmp(id, name) {
    if (!confirm(`Supprimer le profil SNMP "${name}" ?`)) return;
    try { await exec(`DELETE FROM auth_snmp WHERE id = $1`, [id]); loadSnmp(); }
    catch (e) { alert('Erreur : ' + e.message); }
}

async function saveSnmp() {
    const name    = document.querySelector('#modal-snmp input[placeholder="SNMP-Prod-v2c"]').value.trim();
    const version = document.getElementById('snmp-version').value;
    const port    = parseInt(document.querySelector('#modal-snmp input[type="number"]').value) || 161;
    if (!name) { alert('Le nom est obligatoire.'); return; }
    try {
        if (version !== 'v3') {
            const community = document.querySelector('#snmp-v2-block input').value.trim() || null;
            await exec(
                `INSERT INTO auth_snmp (name, version, port, community) VALUES ($1, $2, $3, $4)`,
                [name, version, port, community]
            );
        } else {
            const v3_user       = document.querySelector('#snmp-v3-block input[placeholder="orion_user"]').value.trim();
            const selects       = document.querySelectorAll('#snmp-v3-block select');
            const passwords     = document.querySelectorAll('#snmp-v3-block input[type="password"]');
            await exec(
                `INSERT INTO auth_snmp
                    (name, version, port, v3_user, v3_level, v3_auth_proto, v3_auth_pass, v3_priv_proto, v3_priv_pass)
                 VALUES ($1, 'v3', $2, $3, $4, $5, $6, $7, $8)`,
                [name, port, v3_user,
                 selects[0]?.value, selects[1]?.value, passwords[0]?.value || null,
                 selects[2]?.value, passwords[1]?.value || null]
            );
        }
        closeModal('modal-snmp'); loadSnmp();
    } catch (e) { alert('Erreur : ' + e.message); }
}


/* ════════════════════════════════════════════════════════
   ██  SSH — auth_cli
   Champs : name, username, password, enable_password,
            ssh_key_path, protocol_pref, port
════════════════════════════════════════════════════════ */
async function loadCli() {
    cardLoading('ssh-list');
    try {
        const rows = await sql(`
            SELECT id, name, username, protocol_pref, port, ssh_key_path
            FROM auth_cli ORDER BY name
        `);
        if (!rows.length) { cardEmpty('ssh-list', 'Aucun profil SSH configuré.'); return; }
        document.getElementById('ssh-list').innerHTML = rows.map(c => `
            <div class="config-card">
                <div class="card-info">
                    <div class="card-name">
                        ${c.name}
                        <span class="badge ${c.protocol_pref === 'SSH' ? 'badge-teal' : 'badge-yellow'}">${c.protocol_pref}</span>
                    </div>
                    <div class="card-meta">
                        <span>Utilisateur : <strong>${c.username}</strong></span>
                        <span>Port : <strong>${c.port}</strong></span>
                        ${c.ssh_key_path ? `<span>🔑 <code>${c.ssh_key_path}</code></span>` : '<span>🔒 Mot de passe</span>'}
                    </div>
                </div>
                <div class="card-actions">
                    <button class="btn-icon btn-icon-danger" onclick="deleteCli(${c.id}, '${c.name.replace(/'/g, "\\'")}')">🗑</button>
                </div>
            </div>`).join('');
    } catch (e) { cardError('ssh-list', e.message); }
}

async function deleteCli(id, name) {
    if (!confirm(`Supprimer le profil SSH "${name}" ?`)) return;
    try { await exec(`DELETE FROM auth_cli WHERE id = $1`, [id]); loadCli(); }
    catch (e) { alert('Erreur : ' + e.message); }
}

async function saveCli() {
    const name     = document.querySelector('#modal-ssh input[placeholder="SSH-Cisco-Prod"]').value.trim();
    const proto    = document.querySelector('#modal-ssh select').value;
    const port     = parseInt(document.querySelectorAll('#modal-ssh input[type="number"]')[0]?.value) || 22;
    const username = document.querySelector('#modal-ssh input[placeholder="admin"]').value.trim();
    const password = document.querySelectorAll('#modal-ssh input[type="password"]')[0]?.value || null;
    const enable   = document.querySelectorAll('#modal-ssh input[type="password"]')[1]?.value || null;
    const keypath  = document.querySelector('#modal-ssh input[placeholder="/keys/prod.pem"]').value.trim() || null;
    if (!name || !username) { alert('Nom et utilisateur obligatoires.'); return; }
    try {
        await exec(
            `INSERT INTO auth_cli (name, username, password, enable_password, ssh_key_path, protocol_pref, port)
             VALUES ($1, $2, $3, $4, $5, $6, $7)`,
            [name, username, password, enable, keypath, proto, port]
        );
        closeModal('modal-ssh'); loadCli();
    } catch (e) { alert('Erreur : ' + e.message); }
}


/* ════════════════════════════════════════════════════════
   ██  PROFILS D'ACCÈS — auth_profiles
   Champs : name, snmp_id, cli_id
════════════════════════════════════════════════════════ */
async function loadProfiles() {
    cardLoading('profiles-list');
    try {
        const [rows, snmpRows, cliRows] = await Promise.all([
            sql(`
                SELECT ap.id, ap.name,
                       s.name AS snmp_name, s.version AS snmp_version,
                       c.name AS cli_name,  c.protocol_pref
                FROM auth_profiles ap
                LEFT JOIN auth_snmp s ON ap.snmp_id = s.id
                LEFT JOIN auth_cli  c ON ap.cli_id  = c.id
                ORDER BY ap.name
            `),
            sql(`SELECT id, name, version FROM auth_snmp ORDER BY name`),
            sql(`SELECT id, name, protocol_pref FROM auth_cli ORDER BY name`),
        ]);
        if (!rows.length) { cardEmpty('profiles-list', "Aucun profil d'accès configuré."); }
        else {
            document.getElementById('profiles-list').innerHTML = rows.map(p => `
                <div class="config-card">
                    <div class="card-info">
                        <div class="card-name">${p.name}</div>
                        <div class="card-meta">
                            <span>SNMP : ${p.snmp_name
                                ? `<strong>${p.snmp_name}</strong> <span class="badge badge-teal">${p.snmp_version}</span>`
                                : '<span class="badge badge-gray">Aucun</span>'}</span>
                            <span>SSH : ${p.cli_name
                                ? `<strong>${p.cli_name}</strong> <span class="badge badge-teal">${p.protocol_pref}</span>`
                                : '<span class="badge badge-gray">Aucun</span>'}</span>
                        </div>
                    </div>
                    <div class="card-actions">
                        <button class="btn-icon btn-icon-danger" onclick="deleteProfile(${p.id}, '${p.name.replace(/'/g, "\\'")}')">🗑</button>
                    </div>
                </div>`).join('');
        }
        populateSelect('select-snmp-profile', snmpRows, r => `${r.name} (${r.version})`);
        populateSelect('select-cli-profile',  cliRows,  r => `${r.name} (${r.protocol_pref})`);
    } catch (e) { cardError('profiles-list', e.message); }
}

async function deleteProfile(id, name) {
    if (!confirm(`Supprimer le profil "${name}" ?`)) return;
    try { await exec(`DELETE FROM auth_profiles WHERE id = $1`, [id]); loadProfiles(); }
    catch (e) { alert('Erreur : ' + e.message); }
}

async function saveProfile() {
    const name    = document.querySelector('#modal-profile input[placeholder="Profil-Core-Cisco"]').value.trim();
    const snmp_id = document.getElementById('select-snmp-profile').value || null;
    const cli_id  = document.getElementById('select-cli-profile').value  || null;
    if (!name) { alert('Le nom est obligatoire.'); return; }
    try {
        await exec(
            `INSERT INTO auth_profiles (name, snmp_id, cli_id) VALUES ($1, $2, $3)`,
            [name, snmp_id ? parseInt(snmp_id) : null, cli_id ? parseInt(cli_id) : null]
        );
        closeModal('modal-profile'); loadProfiles();
    } catch (e) { alert('Erreur : ' + e.message); }
}


/* ════════════════════════════════════════════════════════
   ██  PROFILS DE SCAN — scan_profiles
   Champs CLI : name, type, timeout_ms, retry_count,
                concurrency_threads, is_enabled
   Extras BDD : packet_delay_ms (conservé)
════════════════════════════════════════════════════════ */
async function loadScanProfiles() {
    cardLoading('scan-list');
    try {
        const rows = await sql(`
            SELECT id, name, type, interval_seconds, timeout_ms, retry_count,
                   concurrency_threads, packet_delay_ms, is_enabled
            FROM scan_profiles ORDER BY name
        `);
        if (!rows.length) { cardEmpty('scan-list', 'Aucun profil de scan configuré.'); return; }
        document.getElementById('scan-list').innerHTML = rows.map(sp => {
            const on = pgBool(sp.is_enabled);
            return `
            <div class="config-card">
                <div class="card-info">
                    <div class="card-name">
                        ${sp.name}
                        <span class="badge ${on ? 'badge-green' : 'badge-gray'}">${on ? 'Actif' : 'Inactif'}</span>
                        <span class="badge badge-teal">${sp.type}</span>
                    </div>
                    <div class="card-meta">
                        <span>Timeout : <strong>${sp.timeout_ms} ms</strong></span>
                        <span>Retry : <strong>${sp.retry_count}</strong></span>
                        <span>Threads : <strong>${sp.concurrency_threads}</strong></span>
                        <span>Intervalle : <strong>${fmtInterval(sp.interval_seconds)}</strong></span>
                        ${sp.packet_delay_ms > 0 ? `<span>Délai : ${sp.packet_delay_ms} ms</span>` : ''}
                    </div>
                </div>
                <div class="card-actions">
                    <button class="btn-icon" onclick="toggleScanProfile(${sp.id}, ${on})">${on ? '⏸' : '▶'}</button>
                    <button class="btn-icon btn-icon-danger" onclick="deleteScanProfile(${sp.id}, '${sp.name.replace(/'/g, "\\'")}')">🗑</button>
                </div>
            </div>`;
        }).join('');
    } catch (e) { cardError('scan-list', e.message); }
}

async function toggleScanProfile(id, current) {
    try {
        await exec(
            `UPDATE scan_profiles SET is_enabled = $1, updated_at = NOW() WHERE id = $2`,
            [!pgBool(current), id]
        );
        loadScanProfiles();
    } catch (e) { alert('Erreur : ' + e.message); }
}

async function deleteScanProfile(id, name) {
    if (!confirm(`Supprimer le profil de scan "${name}" ?`)) return;
    try { await exec(`DELETE FROM scan_profiles WHERE id = $1`, [id]); loadScanProfiles(); }
    catch (e) { alert('Erreur : ' + e.message); }
}

async function saveScanProfile() {
    const name     = document.querySelector('#modal-scan input[placeholder="SNMP Discovery - Rapide"]').value.trim();
    const type     = document.getElementById('scan-type-select').value;
    const interval = parseInt(document.getElementById('scan-interval').value) || 3600;
    const timeout  = parseInt(document.getElementById('scan-timeout').value)  || 2000;
    const retry    = parseInt(document.getElementById('scan-retry').value)    ?? 1;
    const threads  = parseInt(document.getElementById('scan-threads').value)  || 20;
    const delay    = parseInt(document.getElementById('scan-delay').value)    || 0;
    const enabled  = document.getElementById('scan-enabled').checked;
    if (!name) { alert('Le nom est obligatoire.'); return; }
    try {
        await exec(
            `INSERT INTO scan_profiles
                (name, type, interval_seconds, timeout_ms, retry_count, concurrency_threads, packet_delay_ms, is_enabled)
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
            [name, type, interval, timeout, retry, threads, delay, enabled]
        );
        closeModal('modal-scan'); loadScanProfiles();
    } catch (e) { alert('Erreur : ' + e.message); }
}


/* ════════════════════════════════════════════════════════
   ██  RÉSEAUX — scan_networks
   Champs CLI create : subnet, exclude_ips, description,
                       scan_profile_id, auth_profile_id,
                       interval_seconds, last_scan_status='idle'
   Champs CLI status : + last_scan_at, last_scan_duration,
                         last_hosts_found, last_error, next_scan_at
   Pas de ban (snmp_credentials_mapping retiré)
════════════════════════════════════════════════════════ */
async function loadNetworks() {
    cardLoading('network-list');
    try {
        const [scanRows, scanProfs, authProfs] = await Promise.all([
            sql(`
                SELECT sn.id, sn.subnet::text, sn.description,
                       sn.exclude_ips, sn.interval_seconds, sn.next_scan_at,
                       sn.last_scan_status, sn.last_scan_at,
                       sn.last_scan_duration, sn.last_hosts_found, sn.last_error,
                       sp.name AS scan_profile,
                       ap.name AS auth_profile
                FROM scan_networks sn
                JOIN scan_profiles sp ON sn.scan_profile_id = sp.id
                JOIN auth_profiles ap ON sn.auth_profile_id = ap.id
                ORDER BY sn.subnet
            `),
            sql(`SELECT id, name FROM scan_profiles WHERE is_enabled = TRUE ORDER BY name`),
            sql(`SELECT id, name FROM auth_profiles ORDER BY name`),
        ]);

        if (!scanRows.length) { cardEmpty('network-list', 'Aucun réseau configuré.'); }
        else {
            document.getElementById('network-list').innerHTML = scanRows.map(n => {
                const nextAt = n.next_scan_at ? new Date(n.next_scan_at).toLocaleString('fr-FR') : null;
                const lastAt = n.last_scan_at ? new Date(n.last_scan_at).toLocaleString('fr-FR') : null;
                let excludeStr = '';
                try {
                    const exc = typeof n.exclude_ips === 'string' ? JSON.parse(n.exclude_ips) : (n.exclude_ips || []);
                    if (exc.length) excludeStr = exc.join(', ');
                } catch (_) {}
                return `
                <div class="config-card scan-status-${n.last_scan_status}">
                    <div class="card-info">
                        <div class="card-name">
                            <code>${n.subnet}</code>
                            ${n.description ? `<span style="font-weight:400;color:#666">${n.description}</span>` : ''}
                            <span class="badge ${SCAN_STATUS[n.last_scan_status] || 'badge-gray'}">${n.last_scan_status}</span>
                        </div>
                        <div class="card-meta">
                            <span>Scan : <strong>${n.scan_profile}</strong></span>
                            <span>Auth : <strong>${n.auth_profile}</strong></span>
                            <span>🔁 ${fmtInterval(n.interval_seconds)}</span>
                            ${lastAt             ? `<span>Dernier : ${lastAt}</span>` : ''}
                            ${n.last_hosts_found ? `<span><strong>${n.last_hosts_found}</strong> hôtes</span>` : ''}
                            ${n.last_scan_duration ? `<span>${n.last_scan_duration}s</span>` : ''}
                            ${nextAt             ? `<span>Prochain : ${nextAt}</span>` : ''}
                            ${excludeStr         ? `<span>Exclu : <code>${excludeStr}</code></span>` : ''}
                            ${n.last_error       ? `<span style="color:#ef4444">⚠ ${n.last_error}</span>` : ''}
                        </div>
                    </div>
                    <div class="card-actions">
                        <button class="btn-icon btn-icon-danger" onclick="deleteNetwork(${n.id}, '${n.subnet}')">🗑</button>
                    </div>
                </div>`;
            }).join('');
        }
        populateSelect('select-net-scan-profile', scanProfs, r => r.name);
        populateSelect('select-net-auth-profile', authProfs, r => r.name);
    } catch (e) { cardError('network-list', e.message); }
}

async function deleteNetwork(id, subnet) {
    if (!confirm(`Supprimer le réseau ${subnet} ?`)) return;
    try { await exec(`DELETE FROM scan_networks WHERE id = $1`, [id]); loadNetworks(); }
    catch (e) { alert('Erreur : ' + e.message); }
}

async function saveNetwork() {
    const subnet   = document.getElementById('net-subnet').value.trim();
    const desc     = document.getElementById('net-desc').value.trim() || null;
    const excRaw   = document.getElementById('net-exclude').value.trim();
    const exclude  = excRaw ? JSON.stringify(excRaw.split(',').map(s => s.trim()).filter(Boolean)) : '[]';
    const scan_id  = parseInt(document.getElementById('select-net-scan-profile').value);
    const auth_id  = parseInt(document.getElementById('select-net-auth-profile').value);
    const interval = parseInt(document.getElementById('net-interval').value) ?? 3600;
    if (!subnet)              { alert('Le sous-réseau est obligatoire.'); return; }
    if (!scan_id || !auth_id) { alert("Profil de scan et profil d'accès obligatoires."); return; }
    try {
        await exec(
            `INSERT INTO scan_networks
                (subnet, description, exclude_ips, scan_profile_id, auth_profile_id,
                 interval_seconds, last_scan_status)
             VALUES ($1::cidr, $2, $3::jsonb, $4, $5, $6, 'idle')`,
            [subnet, desc, exclude, scan_id, auth_id, interval]
        );
        closeModal('modal-network'); loadNetworks();
    } catch (e) { alert('Erreur : ' + e.message); }
}


/* ════════════════════════════════════════════════════════
   ██  COULEURS DES LIENS — map_style_media
════════════════════════════════════════════════════════ */
const LINK_LABELS = {
    Copper: 'Cuivre', Fiber: 'Fibre optique', Wireless: 'Sans fil',
    Aggregate: 'LAG / Agrégat', Virtual: 'Virtuel / Overlay', Backplane: 'Backplane / Châssis',
};

async function loadLinkColors() {
    cardLoading('link-colors-list');
    try {
        const rows = await sql(`SELECT id, link_type, base_color, dash_array FROM map_style_media ORDER BY link_type`);
        _cache.linkColors = rows;
        if (!rows.length) { cardEmpty('link-colors-list', 'Aucune donnée.'); return; }
        document.getElementById('link-colors-list').innerHTML = rows.map(lc => `
            <div class="config-card card-media" style="border-left-color:${lc.base_color}">
                <div class="card-info">
                    <div class="card-name">
                        <span style="width:13px;height:13px;border-radius:50%;background:${lc.base_color};border:2px solid rgba(0,0,0,.1);display:inline-block;flex-shrink:0"></span>
                        ${LINK_LABELS[lc.link_type] || lc.link_type}
                        <span style="color:#888;font-weight:400;font-size:.85em">(${lc.link_type})</span>
                    </div>
                    <div class="card-meta">
                        <span>${dashSvg(lc.base_color, lc.dash_array)}</span>
                        <span>${dashLabel(lc.dash_array)}</span>
                        <span><code>${lc.base_color}</code></span>
                    </div>
                </div>
                <div class="card-actions">
                    <button class="btn-icon" onclick="pickLinkColor('${lc.link_type}')">🎨 Couleur</button>
                    <button class="btn-icon" onclick="cycleLinkDash('${lc.link_type}')">〰 Style</button>
                </div>
            </div>`).join('');
    } catch (e) { cardError('link-colors-list', e.message); }
}

function pickLinkColor(type) {
    const row = _cache.linkColors.find(l => l.link_type === type);
    if (!row) return;
    nativePick(row.base_color, async color => {
        try { await exec(`UPDATE map_style_media SET base_color = $1 WHERE link_type = $2`, [color, type]); loadLinkColors(); }
        catch (e) { alert('Erreur : ' + e.message); }
    });
}

async function cycleLinkDash(type) {
    const row = _cache.linkColors.find(l => l.link_type === type);
    if (!row) return;
    const next = DASH_CYCLE[(DASH_CYCLE.indexOf(row.dash_array) + 1) % DASH_CYCLE.length];
    try { await exec(`UPDATE map_style_media SET dash_array = $1 WHERE link_type = $2`, [next, type]); loadLinkColors(); }
    catch (e) { alert('Erreur : ' + e.message); }
}


/* ════════════════════════════════════════════════════════
   ██  ÉPAISSEUR — map_style_thickness
════════════════════════════════════════════════════════ */
async function loadThickness() {
    cardLoading('thickness-list');
    try {
        const rows = await sql(`SELECT id, name, min_bps, max_bps, thickness_px FROM map_style_thickness ORDER BY min_bps`);
        if (!rows.length) { cardEmpty('thickness-list', 'Aucune plage configurée.'); return; }
        document.getElementById('thickness-list').innerHTML = rows.map(t => `
            <div class="config-card">
                <div class="card-info">
                    <div class="card-name">${t.name}</div>
                    <div class="card-meta">
                        <span>${bpsHuman(t.min_bps)} → ${t.max_bps >= 9e14 ? '∞' : bpsHuman(t.max_bps)}</span>
                        <span>${thickSvg(t.thickness_px)}</span>
                        <span><strong>${t.thickness_px} px</strong></span>
                    </div>
                </div>
                <div class="card-actions">
                    <button class="btn-icon btn-icon-danger" onclick="deleteThickness(${t.id}, '${t.name.replace(/'/g, "\\'")}')">🗑</button>
                </div>
            </div>`).join('');
    } catch (e) { cardError('thickness-list', e.message); }
}

async function deleteThickness(id, name) {
    if (!confirm(`Supprimer la plage "${name}" ?`)) return;
    try { await exec(`DELETE FROM map_style_thickness WHERE id = $1`, [id]); loadThickness(); }
    catch (e) { alert('Erreur : ' + e.message); }
}

async function saveThickness() {
    const name = document.querySelector('#modal-thickness input[placeholder="1G – 10G"]').value.trim();
    const min  = parseInt(document.getElementById('thick-min').value);
    const max  = parseInt(document.getElementById('thick-max').value);
    const px   = parseInt(document.querySelector('#modal-thickness input[type="range"]')?.value) || 2;
    if (!name || isNaN(min) || isNaN(max)) { alert('Tous les champs sont obligatoires.'); return; }
    if (max <= min) { alert('Le débit max doit être supérieur au débit min.'); return; }
    try {
        await exec(`INSERT INTO map_style_thickness (name, min_bps, max_bps, thickness_px) VALUES ($1, $2, $3, $4)`,
            [name, min, max, px]);
        closeModal('modal-thickness'); loadThickness();
    } catch (e) { alert('Erreur : ' + e.message); }
}


/* ════════════════════════════════════════════════════════
   ██  STATUTS CARTE — map_status
════════════════════════════════════════════════════════ */
async function loadMapStatus() {
    cardLoading('map-status-list');
    try {
        const rows = await sql(`SELECT id, metric_type, color FROM map_status ORDER BY metric_type`);
        _cache.mapStatus = rows;
        if (!rows.length) { cardEmpty('map-status-list', 'Aucun statut configuré.'); return; }
        document.getElementById('map-status-list').innerHTML = rows.map(s => `
            <div class="config-card" style="border-left-color:${s.color}">
                <div class="card-info">
                    <div class="card-name">
                        <span style="width:18px;height:18px;border-radius:50%;background:${s.color};border:2px solid rgba(0,0,0,.1);display:inline-block;flex-shrink:0"></span>
                        ${s.metric_type}
                    </div>
                    <div class="card-meta"><code>${s.color}</code></div>
                </div>
                <div class="card-actions">
                    <button class="btn-icon" onclick="pickStatusColor('${s.metric_type}')">🎨 Couleur</button>
                </div>
            </div>`).join('');
    } catch (e) { cardError('map-status-list', e.message); }
}

function pickStatusColor(type) {
    const row = _cache.mapStatus.find(s => s.metric_type === type);
    if (!row) return;
    nativePick(row.color, async color => {
        try { await exec(`UPDATE map_status SET color = $1 WHERE metric_type = $2`, [color, type]); loadMapStatus(); }
        catch (e) { alert('Erreur : ' + e.message); }
    });
}


/* ════════════════════════════════════════════════════════
   ██  SÉVÉRITÉS — ref_alert_severity
════════════════════════════════════════════════════════ */
async function loadSeverities() {
    cardLoading('severity-list');
    try {
        const rows = await sql(`SELECT level, name, slug, color, notify FROM ref_alert_severity ORDER BY level DESC`);
        if (!rows.length) { cardEmpty('severity-list', 'Aucun niveau de sévérité.'); return; }
        document.getElementById('severity-list').innerHTML = rows.map(s => {
            const on = pgBool(s.notify);
            return `
            <div class="config-card" style="border-left-color:${s.color}">
                <div class="card-info">
                    <div class="card-name">
                        <span style="width:13px;height:13px;border-radius:50%;background:${s.color};border:2px solid rgba(0,0,0,.1);display:inline-block;flex-shrink:0"></span>
                        Niveau ${s.level} — <strong>${s.name}</strong>
                        <code style="font-size:.8em">${s.slug}</code>
                    </div>
                    <div class="card-meta">
                        <code>${s.color}</code>
                        ${on ? '<span class="badge badge-teal">🔔 Notification active</span>'
                             : '<span class="badge badge-gray">Silencieux</span>'}
                    </div>
                </div>
                <div class="card-actions">
                    <button class="btn-icon" onclick="toggleSeverityNotify(${s.level}, ${on})">
                        ${on ? '🔕 Désactiver' : '🔔 Activer'}
                    </button>
                </div>
            </div>`;
        }).join('');
    } catch (e) { cardError('severity-list', e.message); }
}

async function toggleSeverityNotify(level, current) {
    try {
        await exec(`UPDATE ref_alert_severity SET notify = $1 WHERE level = $2`, [!pgBool(current), level]);
        loadSeverities();
    } catch (e) { alert('Erreur : ' + e.message); }
}


/* ════════════════════════════════════════════════════════
   ██  UTILISATEURS — app_users + user_groups + app_users_pwd
════════════════════════════════════════════════════════ */
async function loadUsers() {
    cardLoading('users-list');
    try {
        const rows = await sql(`
            SELECT u.id, u.username, u.email, u.first_name, u.last_name,
                   u.auth_source, u.is_active, u.is_super_admin, u.last_login,
                   STRING_AGG(g.name, ', ' ORDER BY g.name) AS groupes
            FROM app_users u
            LEFT JOIN user_group_members m ON u.id = m.user_id
            LEFT JOIN user_groups g        ON m.group_id = g.id
            GROUP BY u.id
            ORDER BY u.username
        `);
        if (!rows.length) { cardEmpty('users-list', 'Aucun utilisateur.'); return; }
        document.getElementById('users-list').innerHTML = rows.map(u => {
            const active = pgBool(u.is_active);
            const admin  = pgBool(u.is_super_admin);
            return `
            <div class="config-card">
                <div class="card-info">
                    <div class="card-name">
                        ${u.first_name || ''} ${u.last_name || ''}
                        <span style="color:#888;font-weight:400">(${u.username})</span>
                        ${admin  ? '<span class="badge badge-red">Super Admin</span>' : ''}
                        ${!active ? '<span class="badge badge-gray">Désactivé</span>' : ''}
                    </div>
                    <div class="card-meta">
                        <span>${u.email}</span>
                        <span class="badge ${SOURCE_BADGE[u.auth_source] || 'badge-gray'}">${u.auth_source}</span>
                        ${u.groupes    ? `<span>${u.groupes}</span>` : ''}
                        ${u.last_login ? `<span>Connexion : ${new Date(u.last_login).toLocaleString('fr-FR')}</span>` : ''}
                    </div>
                </div>
                <div class="card-actions">
                    <button class="btn-icon" onclick="toggleUser(${u.id}, ${active})">
                        ${active ? '⛔ Désactiver' : '✅ Activer'}
                    </button>
                    ${!admin ? `<button class="btn-icon btn-icon-danger" onclick="deleteUser(${u.id}, '${u.username.replace(/'/g, "\\'")}')">🗑</button>` : ''}
                </div>
            </div>`;
        }).join('');
    } catch (e) { cardError('users-list', e.message); }
}

async function toggleUser(id, current) {
    const active = pgBool(current);
    if (!confirm(`${active ? 'Désactiver' : 'Activer'} cet utilisateur ?`)) return;
    try {
        await exec(`UPDATE app_users SET is_active = $1, updated_at = NOW() WHERE id = $2`, [!active, id]);
        loadUsers();
    } catch (e) { alert('Erreur : ' + e.message); }
}

async function deleteUser(id, username) {
    if (!confirm(`Supprimer l'utilisateur "${username}" ? Action irréversible.`)) return;
    try { await exec(`DELETE FROM app_users WHERE id = $1`, [id]); loadUsers(); }
    catch (e) { alert('Erreur : ' + e.message); }
}

async function saveUser() {
    const fn       = document.querySelector('#modal-user input[placeholder="Jean"]').value.trim()              || null;
    const ln       = document.querySelector('#modal-user input[placeholder="Dupont"]').value.trim()             || null;
    const username = document.querySelector('#modal-user input[placeholder="jdupont"]').value.trim();
    const email    = document.querySelector('#modal-user input[placeholder="jdupont@corp.local"]').value.trim();
    const password = document.querySelector('#modal-user input[type="password"]').value;
    const isAdmin  = document.querySelector('#modal-user input[type="checkbox"]')?.checked ?? false;
    if (!username || !email || !password) { alert('Identifiant, email et mot de passe obligatoires.'); return; }
    try {
        const res = await exec(
            `INSERT INTO app_users (username, email, first_name, last_name, auth_source, is_super_admin)
             VALUES ($1, $2, $3, $4, 'Local', $5) RETURNING id`,
            [username, email, fn, ln, isAdmin]
        );
        const userId = res.rows?.[0]?.id;
        if (userId) {
            await exec(
                `INSERT INTO app_users_pwd (user_id, password_hash, must_change_pwd) VALUES ($1, $2, FALSE)`,
                [userId, password]
            );
        }
        closeModal('modal-user'); loadUsers();
    } catch (e) { alert('Erreur : ' + e.message); }
}


/* ════════════════════════════════════════════════════════
   ██  RÉTENTION — logs_retention_policy
════════════════════════════════════════════════════════ */
async function loadRetention() {
    cardLoading('retention-list');
    try {
        const rows = await sql(`
            SELECT id, log_table, retention_days, archive_status
            FROM logs_retention_policy ORDER BY log_table
        `);
        if (!rows.length) { cardEmpty('retention-list', 'Aucune règle de rétention configurée.'); return; }
        document.getElementById('retention-list').innerHTML = rows.map(r => {
            const archived = pgBool(r.archive_status);
            return `
            <div class="config-card">
                <div class="card-info">
                    <div class="card-name"><code>${r.log_table}</code></div>
                    <div class="card-meta">
                        <span><strong>${r.retention_days} jours</strong></span>
                        <span>Archive CSV : ${archived
                            ? '<span class="badge badge-teal">Oui</span>'
                            : '<span class="badge badge-gray">Non</span>'}</span>

                    </div>
                </div>
                <div class="card-actions">
                    <button class="btn-icon btn-icon-danger" onclick="deleteRetention(${r.id}, '${r.log_table}')">🗑</button>
                </div>
            </div>`;
        }).join('');
    } catch (e) { cardError('retention-list', e.message); }
}

async function deleteRetention(id, table) {
    if (!confirm(`Supprimer la règle pour "${table}" ?`)) return;
    try { await exec(`DELETE FROM logs_retention_policy WHERE id = $1`, [id]); loadRetention(); }
    catch (e) { alert('Erreur : ' + e.message); }
}

async function saveRetention() {
    const table   = document.querySelector('#modal-retention select').value;
    const days    = parseInt(document.querySelector('#modal-retention input[type="number"]').value);
    const archive = document.querySelector('#modal-retention input[type="checkbox"]')?.checked ?? false;
    if (!table || isNaN(days) || days < 1) { alert('Table et durée obligatoires (min 1 jour).'); return; }
    try {
        await exec(
            `INSERT INTO logs_retention_policy (log_table, retention_days, archive_status)
             VALUES ($1, $2, $3)
             ON CONFLICT (log_table)
             DO UPDATE SET retention_days = $2, archive_status = $3, updated_at = NOW()`,
            [table, days, archive]
        );
        closeModal('modal-retention'); loadRetention();
    } catch (e) { alert('Erreur : ' + e.message); }
}


/* ════════════════════════════════════════════════════════
   UTILITAIRE — color picker natif
════════════════════════════════════════════════════════ */
function nativePick(currentColor, onPick) {
    const input = document.createElement('input');
    input.type  = 'color';
    input.value = currentColor;
    Object.assign(input.style, { position: 'fixed', opacity: '0', left: '-999px' });
    document.body.appendChild(input);
    input.click();
    input.addEventListener('change', () => { onPick(input.value); document.body.removeChild(input); });
    input.addEventListener('blur',   () => { setTimeout(() => document.body.contains(input) && document.body.removeChild(input), 300); });
}


/* ════════════════════════════════════════════════════════
   INIT
════════════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {
    const saves = [
        ['modal-snmp',      saveSnmp],
        ['modal-ssh',       saveCli],
        ['modal-profile',   saveProfile],
        ['modal-scan',      saveScanProfile],
        ['modal-network',   saveNetwork],
        ['modal-thickness', saveThickness],
        ['modal-user',      saveUser],
        ['modal-retention', saveRetention],
    ];
    saves.forEach(([id, fn]) => {
        const btns = document.querySelectorAll(`#${id} .modal-actions .btn-primary`);
        const btn  = btns[btns.length - 1];
        if (btn) btn.addEventListener('click', fn);
    });

    loadSnmp();
    loadCli();
    loadProfiles();
    loadScanProfiles();
    loadNetworks();
    loadLinkColors();
    loadThickness();
    loadMapStatus();
    loadSeverities();
    loadUsers();
    loadRetention();
});