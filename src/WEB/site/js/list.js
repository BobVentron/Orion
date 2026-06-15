'use strict';

// ─────────────────────────────────────────────
// CONFIG
// ─────────────────────────────────────────────
const API_BASE = '/api';

// ─────────────────────────────────────────────
// API — POST /sql  { sql, params }
// ─────────────────────────────────────────────
async function sql(query, params = []) {
    const res = await fetch(`${API_BASE}/sql`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sql: query, params })
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error || 'Erreur SQL inconnue');
    return data.rows ?? [];
}

// ─────────────────────────────────────────────
// STATE
// ─────────────────────────────────────────────
let equipements = [];

// ─────────────────────────────────────────────
// CHARGEMENT
// ─────────────────────────────────────────────
async function chargerEquipements() {
    const startTime = performance.now();

    try {
        console.log('🦆 Canard chercheur en action...');

        // Requête principale : devices avec jointures pour avoir
        // hostname, catégorie, statut, vendor, modèle, localisation
        const rows = await sql(
            `SELECT
                d.id::text                          AS id,
                d.hostname,
                d.serial_number,
                dc.name                             AS categorie,
                rds.name                            AS status,
                rds.color                           AS status_color,
                v.name                              AS vendor,
                df.name                             AS famille,
                dm.part_number                      AS modele,
                f.version                           AS firmware,
                COALESCE(l.name, r.name)            AS localisation,
                ds.icmp_status,
                ds.snmp_status,
                ds.last_poll,
                ds.uptime_seconds,
                d.rack_position,
                d.created_at
             FROM devices d
             JOIN device_models  dm  ON d.model_id   = dm.id
             JOIN device_families df ON dm.family_id  = df.id
             JOIN device_categories dc ON df.category_id = dc.id
             JOIN vendors         v   ON df.vendor_id  = v.id
             JOIN ref_device_status rds ON d.status_id = rds.id
             LEFT JOIN firmwares   f   ON d.firmware_id  = f.id
             LEFT JOIN locations   l   ON d.location_id  = l.id
             LEFT JOIN racks       r   ON d.racks_id     = r.id
             LEFT JOIN device_status ds ON d.id = ds.device_id
             ORDER BY d.hostname`
        );

        equipements = rows;

        const duration = (performance.now() - startTime).toFixed(2);
        console.log(`✅ Chargés en ${duration}ms :`, equipements.length);

        document.getElementById('loading-message').style.display = 'none';
        document.getElementById('skeleton-container').style.display = 'none';

        const container = document.getElementById('liste-equipements');
        container.innerHTML = '';
        equipements.forEach(e => ajouterEquipement(container, e));

        const timeInfo = document.createElement('div');
        timeInfo.className = 'loading-time';
        timeInfo.innerHTML = `⏱️ Chargé en ${duration}ms — ${equipements.length} équipement${equipements.length > 1 ? 's' : ''}`;
        container.parentElement.appendChild(timeInfo);

    } catch (error) {
        console.error('❌ Erreur:', error);
        document.getElementById('loading-message').style.display = 'none';
        document.getElementById('skeleton-container').style.display = 'none';

        const message = error.name === 'AbortError'
            ? 'Pas de réponse après 30 secondes'
            : error.message;

        document.getElementById('liste-equipements').innerHTML = `
            <div style="padding:20px;color:#d97706;text-align:center;background:#fef3c7;border-radius:8px;border-left:4px solid #d97706;font-weight:600;">
                ⚠️ Il y a un couac
                <div style="font-size:0.9em;color:#92400e;margin-top:8px;">${message}</div>
            </div>`;
    }
}

// ─────────────────────────────────────────────
// RENDU — une ligne de la liste
// ─────────────────────────────────────────────
function ajouterEquipement(container, eq) {
    const template = document.getElementById('equipement-template');
    const clone    = template.content.cloneNode(true);
    const ligne    = clone.querySelector('.equipement-ligne');

    clone.querySelector('.equipement-nom').textContent       = eq.hostname;
    clone.querySelector('.equipement-categorie').textContent = eq.categorie;

    const statusEl = clone.querySelector('.equipement-status');
    statusEl.textContent = eq.status;
    // Classe CSS basée sur le code de statut (ex: "online", "offline", "maintenance")
    statusEl.className = 'equipement-status status-' + eq.status.toLowerCase().replace(/\s/g, '-');
    // Couleur issue de ref_device_status.color si disponible
    if (eq.status_color) statusEl.style.color = eq.status_color;

    ligne.addEventListener('click', () => afficherPopup(eq));
    container.appendChild(clone);
}

// ─────────────────────────────────────────────
// POPUP — détails d'un équipement
// ─────────────────────────────────────────────
async function afficherPopup(eq) {
    const modal = document.getElementById('modal-details');
    document.getElementById('modal-title').textContent = eq.hostname;
    document.getElementById('modal-body').innerHTML    = '<div style="text-align:center;padding:20px;color:#008080">🦆 Chargement des détails…</div>';
    modal.style.display = 'flex';

    try {
        // Charge les interfaces de cet équipement en complément
        const interfaces = await sql(
            `SELECT i.name, i.description, i.type, i.speed,
                    i.mac_address::text,
                    ips.admin_status, ips.oper_status
             FROM interfaces i
             LEFT JOIN LATERAL (
                 SELECT admin_status, oper_status
                 FROM interfaces_status
                 WHERE interface_id = i.id
                 ORDER BY id DESC
                 LIMIT 1
             ) ips ON TRUE
             WHERE i.device_id = $1
             ORDER BY i.name`,
    [eq.id]
);

        // Champs principaux
        const champsPrincipaux = {
            'Hostname':      eq.hostname,
            'Catégorie':     eq.categorie,
            'Vendor':        eq.vendor,
            'Famille':       eq.famille,
            'Modèle':        eq.modele,
            'Firmware':      eq.firmware,
            'Numéro série':  eq.serial_number,
            'Localisation':  eq.localisation,
            'Position rack': eq.rack_position ? `U${eq.rack_position}` : null,
            'Statut':        eq.status,
            'ICMP':          eq.icmp_status,
            'SNMP':          eq.snmp_status,
            'Uptime':        eq.uptime_seconds ? formatUptime(eq.uptime_seconds) : null,
            'Dernier poll':  eq.last_poll ? new Date(eq.last_poll).toLocaleString('fr-FR') : null,
            'Enregistré le': eq.created_at ? new Date(eq.created_at).toLocaleString('fr-FR') : null,
        };

        let html = '<div class="modal-details-grid">';
        Object.entries(champsPrincipaux).forEach(([label, val]) => {
            if (val !== null && val !== undefined && val !== '') {
                html += `<div class="detail-item">
                    <span class="detail-label">${label}</span>
                    <span class="detail-value">${val}</span>
                </div>`;
            }
        });
        html += '</div>';

        // Section interfaces si présentes
        if (interfaces.length) {
            html += `<div style="margin-top:20px;">
                <div style="font-size:.78em;font-weight:700;color:#008080;text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px;">
                    Interfaces (${interfaces.length})
                </div>
                <div style="display:flex;flex-direction:column;gap:6px;">`;
            interfaces.forEach(iface => {
                const speedStr = iface.speed ? bpsHuman(iface.speed) : '—';
                const operOk   = iface.oper_status === 'Up';
                html += `<div style="display:flex;align-items:center;gap:10px;padding:8px 12px;background:#f8fafb;border-radius:6px;border-left:3px solid ${operOk ? '#22c55e' : '#e0e0e0'}">
                    <span style="font-weight:600;font-size:.9em;min-width:100px">${iface.name}</span>
                    <span style="font-size:.8em;color:#666;flex:1">${iface.description || ''}</span>
                    <span style="font-size:.78em;color:#888">${speedStr}</span>
                    <span style="font-size:.75em;padding:2px 7px;border-radius:8px;font-weight:600;background:${operOk ? '#dcfce7' : '#f1f5f9'};color:${operOk ? '#15803d' : '#475569'}">${iface.oper_status || '—'}</span>
                </div>`;
            });
            html += '</div></div>';
        }

        document.getElementById('modal-body').innerHTML = html;

    } catch (err) {
        // Fallback : affiche juste les champs de base sans interfaces
        let html = '<div class="modal-details-grid">';
        Object.entries(eq).forEach(([key, val]) => {
            if (val !== null && val !== undefined && val !== '') {
                const label = key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, ' ');
                html += `<div class="detail-item">
                    <span class="detail-label">${label}</span>
                    <span class="detail-value">${val}</span>
                </div>`;
            }
        });
        html += '</div>';
        document.getElementById('modal-body').innerHTML = html;
    }
}

// ─────────────────────────────────────────────
// FILTRAGE
// ─────────────────────────────────────────────
function filtrerEquipements(terme) {
    const lignes = document.querySelectorAll('.equipement-ligne');
    let resultats = 0;
    const t = terme.toLowerCase();

    lignes.forEach(ligne => {
        const nom = ligne.querySelector('.equipement-nom').textContent.toLowerCase();
        const cat = ligne.querySelector('.equipement-categorie').textContent.toLowerCase();
        const visible = nom.includes(t) || cat.includes(t);
        ligne.style.display = visible ? 'flex' : 'none';
        if (visible) resultats++;
    });

    const msgAucun = document.getElementById('aucun-resultat');
    if (resultats === 0 && terme !== '') {
        if (!msgAucun) {
            const msg = document.createElement('div');
            msg.id        = 'aucun-resultat';
            msg.className = 'aucun-resultat';
            msg.textContent = 'Aucun équipement trouvé 😔';
            document.getElementById('liste-equipements').parentElement.appendChild(msg);
        }
        document.getElementById('aucun-resultat').style.display = 'block';
    } else if (msgAucun) {
        msgAucun.style.display = 'none';
    }
}

// ─────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────
function bpsHuman(bps) {
    if (bps >= 1e12) return (bps / 1e12).toFixed(0) + ' Tbps';
    if (bps >= 1e9)  return (bps / 1e9).toFixed(0)  + ' Gbps';
    if (bps >= 1e6)  return (bps / 1e6).toFixed(0)  + ' Mbps';
    if (bps >= 1e3)  return (bps / 1e3).toFixed(0)  + ' Kbps';
    return bps + ' bps';
}

function formatUptime(seconds) {
    const d = Math.floor(seconds / 86400);
    const h = Math.floor((seconds % 86400) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (d > 0) return `${d}j ${h}h ${m}m`;
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
}

// ─────────────────────────────────────────────
// INIT
// ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
    chargerEquipements();

    const searchInput = document.getElementById('search-input');
    const clearBtn    = document.getElementById('clear-search');

    if (searchInput && clearBtn) {
        searchInput.addEventListener('input', e => {
            filtrerEquipements(e.target.value);
            clearBtn.style.display = e.target.value ? 'block' : 'none';
        });

        clearBtn.addEventListener('click', () => {
            searchInput.value      = '';
            clearBtn.style.display = 'none';
            filtrerEquipements('');
            searchInput.focus();
        });

        clearBtn.style.display = 'none';
    }

    document.getElementById('close-modal').addEventListener('click', () => {
        document.getElementById('modal-details').style.display = 'none';
    });

    window.addEventListener('click', e => {
        const modal = document.getElementById('modal-details');
        if (e.target === modal) modal.style.display = 'none';
    });
});
