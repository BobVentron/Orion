/* ══════════════════════════════════════════════════════════
   carto.js — Logique de la vue cartographie réseau
   Orion · DuckInc  —  VERSION PRODUCTION (API /api/sql)
══════════════════════════════════════════════════════════ */

'use strict';

/* ════════════════════════════════════════════════════════
   API  —  /api/sql  (production)
════════════════════════════════════════════════════════ */
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

/* ── Constantes ── */
const FA_ICONS = {
  switch: 'fa-network-wired', router: 'fa-random', firewall: 'fa-shield-alt',
  wlc: 'fa-wifi', ap: 'fa-broadcast-tower', server: 'fa-server',
  ups: 'fa-battery-half', printer: 'fa-print', unknown: 'fa-question-circle',
};
const ICONS = {
  switch: '⬡', router: '◈', firewall: '⊠', server: '▣',
  wlc: '📡', ap: '◎', storage: '▤', unknown: '◇',
};
const STATUS_COLORS = { online: '#16a34a', offline: '#dc2626', unknown: '#5a9090' };

/* ── État global ── */
const state = {
  maps: [], currentMap: null,
  allDevices: [], selectedDevIds: new Set(),
  graphNodes: [], graphLinks: [],
  styleMedia: {}, styleThick: [],
  simulation: null,
  showLabels: true, showPorts: false,
  pathMode: false, pathNodes: [],
  activeFilters: new Set(),
  lastRefresh: null,
};

/* ════════════════════════════════════════════════════════
   UTILITAIRES
════════════════════════════════════════════════════════ */
function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function switchTab(name) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.toggle('active', p.id === 'tab-' + name));
}

function toast(msg, type = '') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `show ${type}`;
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.className = ''; }, 3000);
}

function loading(show, text = 'Le canard charge…') {
  document.getElementById('loading').style.display = show ? 'flex' : 'none';
  document.getElementById('loading-text').textContent = text;
}

function bpsH(bps) {
  if (!bps || bps < 0) return '—';
  if (bps >= 1e9) return (bps / 1e9).toFixed(1) + ' Gbps';
  if (bps >= 1e6) return (bps / 1e6).toFixed(0) + ' Mbps';
  if (bps >= 1e3) return (bps / 1e3).toFixed(0) + ' Kbps';
  return bps + ' bps';
}

function fmtUptime(s) {
  if (!s) return null;
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  return d > 0 ? `${d}j ${h}h ${m}m` : h > 0 ? `${h}h ${m}m` : `${m}m`;
}

const row = (k, v, mono = false) =>
  (v != null && v !== '')
    ? `<div class="popup-row"><span class="popup-key">${k}</span><span class="popup-val"${mono ? ' style="font-family:var(--font)"' : ''}>${esc(String(v))}</span></div>`
    : '';

/* ════════════════════════════════════════════════════════
   TABS PANEL
════════════════════════════════════════════════════════ */
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    if (btn.dataset.tab === 'style') loadStyles();
  });
});

/* ════════════════════════════════════════════════════════
   INITIALISATION
════════════════════════════════════════════════════════ */
async function init() {
  loading(true, '🦆 Connexion à la mare…');
  try {
    await Promise.all([loadMaps(), loadAllDevices()]);
    toast('🦆 Réseau chargé !', 'success');
  } catch (e) {
    toast('Impossible de joindre la DB — vérifiez l\'API', 'error');
    console.error(e);
  } finally {
    loading(false);
  }
}

/* ════════════════════════════════════════════════════════
   CARTES
════════════════════════════════════════════════════════ */
async function loadMaps() {
  const maps = await sql(`SELECT id, name, description, created_at FROM maps ORDER BY name`);
  state.maps = maps;
  renderMapList();
}

function renderMapList() {
  const el = document.getElementById('maps-list');
  if (!state.maps.length) {
    el.innerHTML = '<div style="color:var(--text3);font-size:12px;text-align:center;padding:20px">Aucune carte — créez-en une !</div>';
    return;
  }
  el.innerHTML = '';
  state.maps.forEach(m => {
    const card = document.createElement('div');
    card.className = 'map-card' + (state.currentMap?.id === m.id ? ' active' : '');
    card.innerHTML = `
      <div style="flex:1;min-width:0">
        <div class="map-name">${esc(m.name)}</div>
        <div class="map-meta">${m.description ? esc(m.description.slice(0, 50)) : 'Sans description'}</div>
      </div>
      <div class="map-actions">
        <button class="icon-btn" data-action="edit" data-id="${m.id}">✏</button>
      </div>`;
    card.addEventListener('click', e => { if (!e.target.closest('[data-action]')) loadMap(m.id); });
    card.querySelector('[data-action=edit]').addEventListener('click', e => {
      e.stopPropagation(); openEditMap(m.id);
    });
    el.appendChild(card);
  });
}

async function loadMap(mapId) {
  loading(true, 'Chargement de la carte…');
  try {
    const [mapInfo, mapDevices] = await Promise.all([
      sql(`SELECT id, name, description FROM maps WHERE id = $1`, [mapId]),
      sql(`SELECT device_id::text AS device_id, pos_x, pos_y FROM map_devices WHERE map_id = $1`, [mapId]),
    ]);
    state.currentMap = mapInfo[0];
    const devIds = mapDevices.map(d => d.device_id);
    const posMap = Object.fromEntries(mapDevices.map(d => [d.device_id, { x: d.pos_x, y: d.pos_y }]));
    const devices = state.allDevices.filter(d => devIds.includes(d.id));
    const links   = await loadLinks(devIds);
    buildGraph(devices, links, posMap);
    document.getElementById('map-title-display').textContent = state.currentMap.name;
    renderMapList();
  } catch (e) { toast('Erreur chargement carte: ' + e.message, 'error'); }
  finally { loading(false); }
}

/* ════════════════════════════════════════════════════════
   DEVICES
════════════════════════════════════════════════════════ */
async function loadAllDevices() {
  const rows = await sql(
    `SELECT d.id::text AS id, d.hostname, d.snmp_contact, d.snmp_description, d.serial_number,
            dc.slug AS type, dc.name AS category_name, v.name AS vendor,
            df.name AS family_name, df.sysobject_oid,
            dm.part_number AS model, f.version AS firmware,
            COALESCE(l.name, rk.name) AS location,
            ds.icmp_status, ds.snmp_status, ds.uptime_seconds, ds.last_poll,
            host(ipm_ip.address) AS mgmt_ip
     FROM devices d
     JOIN device_models dm ON d.model_id = dm.id
     JOIN device_families df ON dm.family_id = df.id
     JOIN device_categories dc ON df.category_id = dc.id
     JOIN vendors v ON df.vendor_id = v.id
     LEFT JOIN firmwares f ON d.firmware_id = f.id
     LEFT JOIN locations l ON d.location_id = l.id
     LEFT JOIN racks rk ON d.racks_id = rk.id
     LEFT JOIN device_status ds ON d.id = ds.device_id
     LEFT JOIN LATERAL (
         SELECT ia.address
         FROM ip_interface_map ipm2
         JOIN ip_addresses ia ON ia.id = ipm2.ip_address_id
         JOIN interfaces i2 ON i2.id = ipm2.interface_id
         WHERE i2.device_id = d.id AND ipm2.is_primary = TRUE
         LIMIT 1
     ) ipm_ip ON TRUE
     ORDER BY d.hostname`
  );

  state.allDevices = rows.map(d => ({
    id:               d.id,
    hostname:         d.hostname,
    snmp_contact:     d.snmp_contact,
    snmp_description: d.snmp_description,
    serial_number:    d.serial_number,
    type:             d.type || 'unknown',
    category_name:    d.category_name,
    vendor:           d.vendor || '',
    family_name:      d.family_name,
    sysobject_oid:    d.sysobject_oid,
    model:            d.model || '',
    firmware:         d.firmware || '',
    location:         d.location || '',
    uptime:           d.uptime_seconds || null,
    last_poll:        d.last_poll || null,
    ip:               d.mgmt_ip || null,
    status:           d.icmp_status === 'Reachable' ? 'online'
                    : d.icmp_status === 'Unreachable' ? 'offline' : 'unknown',
    icmp_status:      d.icmp_status,
    snmp_status:      d.snmp_status,
  }));

  renderDevicePicker();
  buildFilterBar();
}

/* ════════════════════════════════════════════════════════
   LIENS
════════════════════════════════════════════════════════ */
async function loadLinks(devIds) {
  if (!devIds.length) return [];

  const rows = await sql(
    `WITH dev_ifaces AS (
         SELECT i.id AS if_id, i.device_id::text AS device_id, i.name AS if_name
         FROM interfaces i
         WHERE i.device_id = ANY($1::uuid[])
     )
     SELECT nl.id::text AS link_id,
            nl.src_interface_id::text AS src_interface_id,
            nl.dst_interface_id::text AS dst_interface_id,
            nl.link_type, nl.discovery_proto,
            si.device_id AS src_device, si.if_name AS src_port,
            di.device_id AS dst_device, di.if_name AS dst_port,
            msm.base_color, msm.dash_array,
            mst.thickness_px
     FROM network_links nl
     JOIN dev_ifaces si ON si.if_id = nl.src_interface_id
     JOIN dev_ifaces di ON di.if_id = nl.dst_interface_id
     LEFT JOIN map_style_media msm ON msm.link_type = nl.link_type
     LEFT JOIN map_style_thickness mst ON mst.id = nl.ui_thickness_id`,
    [devIds]
  ).catch(() => []);

  return rows
    .filter(l => l.src_device !== l.dst_device)
    .map(l => ({
      ...l,
      color:     l.base_color  || state.styleMedia[l.link_type]?.base_color || linkColor(l.link_type),
      dash:      l.dash_array  || state.styleMedia[l.link_type]?.dash_array  || null,
      thickness: l.thickness_px || 2,
    }));
}

function linkColor(type) {
  const c = { Copper: '#B87333', Fiber: '#eab308', Wireless: '#3498db', Aggregate: '#9b59b6', Virtual: '#95a5a6', Backplane: '#4a5568' };
  return c[type] || '#555';
}

/* ════════════════════════════════════════════════════════
   DEVICE PICKER
════════════════════════════════════════════════════════ */
function renderDevicePicker(filter = '') {
  const el = document.getElementById('device-picker');
  const filtered = state.allDevices.filter(d =>
    !filter || d.hostname.toLowerCase().includes(filter.toLowerCase()) || (d.ip || '').includes(filter)
  );
  el.innerHTML = '';
  filtered.forEach(d => {
    const div = document.createElement('div');
    div.className = 'device-item' + (state.selectedDevIds.has(d.id) ? ' selected' : '');
    div.innerHTML = `
      <input type="checkbox" class="device-cb" ${state.selectedDevIds.has(d.id) ? 'checked' : ''}>
      <span class="device-icon">${ICONS[d.type] || '◇'}</span>
      <div class="device-info">
        <div class="device-hostname">${esc(d.hostname)}</div>
        <div class="device-ip">${d.ip || '—'} · ${d.type}</div>
      </div>
      <div class="status-dot ${d.status}"></div>`;
    div.addEventListener('click', () => {
      if (state.selectedDevIds.has(d.id)) state.selectedDevIds.delete(d.id);
      else state.selectedDevIds.add(d.id);
      renderDevicePicker(document.getElementById('device-search').value);
      document.getElementById('selected-count').textContent = state.selectedDevIds.size;
    });
    el.appendChild(div);
  });
}
document.getElementById('device-search').addEventListener('input', e => renderDevicePicker(e.target.value));

/* ════════════════════════════════════════════════════════
   ÉDITION CARTE
════════════════════════════════════════════════════════ */
document.getElementById('btn-new-map').addEventListener('click', () => {
  state.currentMap = null;
  state.selectedDevIds.clear();
  document.getElementById('map-name-input').value  = '';
  document.getElementById('map-desc-input').value  = '';
  document.getElementById('selected-count').textContent = '0';
  renderDevicePicker();
  document.getElementById('no-map-selected').style.display = 'none';
  document.getElementById('edit-form').style.display       = 'block';
  document.getElementById('btn-delete-map').style.display  = 'none';
  switchTab('edit');
});

async function openEditMap(mapId) {
  const map = state.maps.find(m => m.id === mapId);
  if (!map) return;
  const mapDevices = await sql(
    `SELECT device_id::text AS device_id FROM map_devices WHERE map_id = $1`, [mapId]
  );
  state.currentMap     = map;
  state.selectedDevIds = new Set(mapDevices.map(d => d.device_id));
  document.getElementById('map-name-input').value  = map.name;
  document.getElementById('map-desc-input').value  = map.description || '';
  document.getElementById('selected-count').textContent = state.selectedDevIds.size;
  renderDevicePicker();
  document.getElementById('no-map-selected').style.display = 'none';
  document.getElementById('edit-form').style.display       = 'block';
  document.getElementById('btn-delete-map').style.display  = 'block';
  switchTab('edit');
}

document.getElementById('btn-cancel-edit').addEventListener('click', () => {
  document.getElementById('edit-form').style.display       = 'none';
  document.getElementById('no-map-selected').style.display = 'block';
});

document.getElementById('btn-save-map').addEventListener('click', async () => {
  const name = document.getElementById('map-name-input').value.trim();
  if (!name)                      { toast('Nom de carte requis', 'error'); return; }
  if (!state.selectedDevIds.size) { toast('Sélectionne au moins un équipement', 'error'); return; }
  loading(true, 'Sauvegarde…');
  try {
    let mapId;
    const desc = document.getElementById('map-desc-input').value;
    if (state.currentMap) {
      await exec(
        `UPDATE maps SET name = $1, description = $2, updated_at = NOW() WHERE id = $3`,
        [name, desc, state.currentMap.id]
      );
      mapId = state.currentMap.id;
      await exec(`DELETE FROM map_devices WHERE map_id = $1`, [mapId]);
    } else {
      const res = await exec(
        `INSERT INTO maps (name, description) VALUES ($1, $2) RETURNING id`,
        [name, desc]
      );
      mapId = res.rows[0].id;
    }
    for (const devId of state.selectedDevIds) {
      await exec(
        `INSERT INTO map_devices (map_id, device_id, pos_x, pos_y)
         VALUES ($1, $2::uuid, 0, 0)
         ON CONFLICT (map_id, device_id) DO NOTHING`,
        [mapId, devId]
      );
    }
    toast('Carte sauvegardée !', 'success');
    await loadMaps();
    await loadMap(mapId);
    document.getElementById('edit-form').style.display       = 'none';
    document.getElementById('no-map-selected').style.display = 'block';
    switchTab('maps');
  } catch (e) { toast('Erreur: ' + e.message, 'error'); }
  finally { loading(false); }
});

document.getElementById('btn-delete-map').addEventListener('click', async () => {
  if (!state.currentMap) return;
  if (!confirm(`Supprimer la carte "${state.currentMap.name}" ?`)) return;
  loading(true);
  try {
    await exec(`DELETE FROM maps WHERE id = $1`, [state.currentMap.id]);
    state.currentMap = null;
    document.getElementById('map-title-display').textContent = '🦆 Aucune carte sélectionnée';
    clearGraph();
    await loadMaps();
    document.getElementById('edit-form').style.display       = 'none';
    document.getElementById('no-map-selected').style.display = 'block';
    switchTab('maps');
    toast('Carte supprimée', 'success');
  } catch (e) { toast('Erreur: ' + e.message, 'error'); }
  finally { loading(false); }
});

/* ════════════════════════════════════════════════════════
   D3 — GRAPHE
════════════════════════════════════════════════════════ */
const svg = d3.select('#map-svg');
const g   = svg.select('#map-g');

const _zoomHandler = d3.zoom()
  .scaleExtent([0.05, 4])
  .on('zoom', e => g.attr('transform', e.transform));

svg.call(_zoomHandler);
svg.on('dblclick.zoom', null);

function fitGraph() {
  const wrap = document.getElementById('map-area');
  const W = wrap.clientWidth, H = wrap.clientHeight;
  const bounds = g.node()?.getBBox();
  if (!bounds || !bounds.width || !bounds.height) return;
  const scale = Math.min(0.9, Math.min(W / (bounds.width + 80), H / (bounds.height + 80)));
  const tx = W / 2 - scale * (bounds.x + bounds.width  / 2);
  const ty = H / 2 - scale * (bounds.y + bounds.height / 2);
  svg.transition().duration(600).call(_zoomHandler.transform, d3.zoomIdentity.translate(tx, ty).scale(scale));
}

function clearGraph() {
  g.selectAll('*').remove();
  state.simulation?.stop();
  document.getElementById('map-area').classList.remove('has-nodes');
  ['stat-nodes', 'stat-links', 'stat-online', 'stat-offline'].forEach(id => {
    document.getElementById(id).textContent = '–';
  });
}

function buildGraph(devices, rawLinks, posMap = {}) {
  clearGraph();
  if (!devices.length) return;

  const linkSet = new Map();
  rawLinks.forEach(l => {
    const key = [l.src_interface_id, l.dst_interface_id].sort().join(':');
    if (!linkSet.has(key)) linkSet.set(key, l);
  });

  const linkGroups = {};
  [...linkSet.values()].forEach(l => {
    const gkey = [l.src_device, l.dst_device].sort().join('|');
    if (!linkGroups[gkey]) linkGroups[gkey] = [];
    linkGroups[gkey].push(l);
  });
  [...linkSet.values()].forEach(l => {
    const gkey = [l.src_device, l.dst_device].sort().join('|');
    const grp = linkGroups[gkey], idx = grp.indexOf(l), count = grp.length;
    l._offset = count === 1 ? 0 : (idx - (count - 1) / 2) * 12;
  });

  function linkPath(d) {
    const sx = d.source.x || 0, sy = d.source.y || 0, tx = d.target.x || 0, ty = d.target.y || 0;
    if (!d._offset) return `M${sx},${sy}L${tx},${ty}`;
    const dx = tx - sx, dy = ty - sy, len = Math.sqrt(dx * dx + dy * dy) || 1;
    const mx = (sx + tx) / 2 + (-dy / len) * d._offset;
    const my = (sy + ty) / 2 + ( dx / len) * d._offset;
    return `M${sx},${sy}Q${mx},${my},${tx},${ty}`;
  }

  const nodes = devices.map(d => ({
    id: d.id, label: d.hostname, ip: d.ip, type: d.type, status: d.status, data: d,
    x:  posMap[d.id]?.x || null,
    y:  posMap[d.id]?.y || null,
    fx: (posMap[d.id]?.x > 0 || posMap[d.id]?.x < 0) ? posMap[d.id].x : null,
    fy: (posMap[d.id]?.y > 0 || posMap[d.id]?.y < 0) ? posMap[d.id].y : null,
  }));

  const nodeById = Object.fromEntries(nodes.map(n => [n.id, n]));
  const links = [...linkSet.values()]
    .map(l => ({ ...l, source: nodeById[l.src_device], target: nodeById[l.dst_device] }))
    .filter(l => l.source && l.target);

  state.graphNodes = nodes;
  state.graphLinks = links;
  document.getElementById('map-area').classList.add('has-nodes');
  document.getElementById('stat-nodes').textContent   = nodes.length;
  document.getElementById('stat-links').textContent   = links.length;
  document.getElementById('stat-online').textContent  = nodes.filter(n => n.status === 'online').length;
  document.getElementById('stat-offline').textContent = nodes.filter(n => n.status === 'offline').length;

  const strength = +document.getElementById('sim-strength').value;
  const distance = +document.getElementById('sim-distance').value;

  state.simulation = d3.forceSimulation(nodes)
    .force('link',      d3.forceLink(links).id(d => d.id).distance(distance))
    .force('charge',    d3.forceManyBody().strength(strength))
    .force('center',    d3.forceCenter(
      document.getElementById('map-area').clientWidth  / 2,
      document.getElementById('map-area').clientHeight / 2
    ))
    .force('collision', d3.forceCollide(50))
    .on('tick', tick);

  const linkEl = g.selectAll('.link-line')
    .data(links).enter().append('path')
    .attr('class', 'link-line')
    .attr('fill', 'none')
    .attr('stroke',           d => d.color || '#555')
    .attr('stroke-width',     d => d.thickness || 2)
    .attr('stroke-dasharray', d => d.dash || null)
    .attr('opacity', 0.7)
    .on('mouseover', function (e, d) {
      d3.select(this).attr('opacity', 1).attr('stroke-width', (d.thickness || 2) + 1.5);
      showLinkTooltip(e, d);
    })
    .on('mousemove', e => _positionLinkTip(e))
    .on('mouseout', function (e, d) {
      d3.select(this).attr('opacity', 0.7).attr('stroke-width', d.thickness || 2);
      hideLinkTooltip();
    });

  const portLabelG = g.selectAll('.port-label-g')
    .data(links).enter().append('g')
    .attr('class', 'port-label-g')
    .attr('display', state.showPorts ? null : 'none');
  portLabelG.append('text').attr('class', 'link-label port-label-src');
  portLabelG.append('text').attr('class', 'link-label port-label-dst');

  const nodeEl = g.selectAll('.node-group')
    .data(nodes).enter().append('g')
    .attr('class', 'node-group')
    .call(d3.drag()
      .on('start', (e, d) => {
        if (!d._unlocked) return;
        if (!e.active) state.simulation.alphaTarget(0.3).restart();
        d.fx = d.x; d.fy = d.y;
      })
      .on('drag',  (e, d) => { if (!d._unlocked) return; d.fx = e.x; d.fy = e.y; })
      .on('end',   (e, d) => { if (!d._unlocked) return; if (!e.active) state.simulation.alphaTarget(0); })
    )
    .on('click', (e, d) => {
      e.stopPropagation();
      if (state.pathMode) { handlePathClick(d); return; }
      showNodePopup(d);
    });

  nodeEl.append('circle').attr('class', 'node-bg').attr('r', 22)
    .attr('fill', d => d.status === 'online' ? '#f0fdf4' : d.status === 'offline' ? '#fff1f2' : '#f0f9f9')
    .attr('stroke', d => STATUS_COLORS[d.status] || '#aaa')
    .attr('stroke-width', 2.5)
    .attr('filter', 'drop-shadow(0 2px 6px rgba(0,0,0,0.10))');

  nodeEl.append('circle').attr('r', 26).attr('fill', 'none')
    .attr('stroke', d => STATUS_COLORS[d.status] || '#aaa')
    .attr('stroke-width', d => d.status === 'offline' ? 1.5 : .5)
    .attr('opacity', d => d.status === 'offline' ? .6 : .25)
    .attr('class', d => d.status === 'offline' ? 'node-offline-ring' : null);

  nodeEl.append('foreignObject').attr('x', -12).attr('y', -12).attr('width', 24).attr('height', 24)
    .style('pointer-events', 'none')
    .append('xhtml:div')
    .style('width', '24px').style('height', '24px')
    .style('display', 'flex').style('align-items', 'center').style('justify-content', 'center')
    .style('font-size', '14px')
    .style('color', d => STATUS_COLORS[d.status] || '#888')
    .html(d => `<i class="fas ${FA_ICONS[d.type] || FA_ICONS.unknown}"></i>`);

  const labelEl = nodeEl.append('text').attr('class', 'node-label')
    .attr('text-anchor', 'middle').attr('dy', 38)
    .attr('font-size', 11).attr('fill', '#2d6060')
    .text(d => d.label.length > 18 ? d.label.slice(0, 16) + '…' : d.label)
    .style('pointer-events', 'none');
  if (!state.showLabels) labelEl.attr('display', 'none');

  svg.on('click', e => { if (!e.target.closest('.node-group')) closeNodePopup(); });

  function tick() {
    linkEl.attr('d', linkPath);
    nodeEl.attr('transform', d => `translate(${d.x || 0},${d.y || 0})`);
    portLabelG.each(function (d) {
      const sx = d.source.x || 0, sy = d.source.y || 0, tx = d.target.x || 0, ty = d.target.y || 0;
      const dx = tx - sx, dy = ty - sy, len = Math.sqrt(dx * dx + dy * dy) || 1;
      const ox = -dy / len * 8, oy = dx / len * 8;
      d3.select(this).select('.port-label-src').attr('x', sx + dx * .22 + ox).attr('y', sy + dy * .22 + oy).text(d.src_port || '');
      d3.select(this).select('.port-label-dst').attr('x', sx + dx * .78 + ox).attr('y', sy + dy * .78 + oy).text(d.dst_port || '');
    });
  }

  setTimeout(() => {
    state.graphNodes.forEach(n => { if (n.fx == null) { n.fx = n.x; n.fy = n.y; } });
    fitGraph();
  }, 2500);
}

/* ════════════════════════════════════════════════════════
   TOOLTIP LIEN
════════════════════════════════════════════════════════ */
let linkTip = null, _linkTimer = null;

function _ensureTip() {
  if (!linkTip) {
    linkTip = document.createElement('div');
    linkTip.style.cssText = 'position:fixed;z-index:150;pointer-events:none;background:#1c2030;border:1px solid #38425a;border-radius:8px;padding:10px 14px;font-size:11px;color:#94a3b8;line-height:1.6;min-width:220px;max-width:300px;box-shadow:0 8px 24px rgba(0,0,0,.5)';
    document.body.appendChild(linkTip);
  }
}

function showLinkTooltip(e, d) {
  _ensureTip();
  linkTip.innerHTML = `
    <div style="color:#e2e8f0;font-weight:600;margin-bottom:6px;display:flex;align-items:center;gap:6px">
      <span style="width:8px;height:8px;border-radius:50%;background:${d.color || '#555'};flex-shrink:0"></span>
      ${esc(d.link_type || 'Lien')} · ${esc(d.discovery_proto || '—')}
    </div>
    <div style="display:flex;gap:12px;margin-bottom:6px">
      <div>📤 <strong>${esc(d.src_port || '—')}</strong></div>
      <div>📥 <strong>${esc(d.dst_port || '—')}</strong></div>
    </div>
    <div id="link-bw-section" style="color:#94a3b8;font-size:10px">⏳ Chargement bande passante…</div>`;
  _positionLinkTip(e);
  linkTip.style.display = 'block';
  clearTimeout(_linkTimer);
  _linkTimer = setTimeout(() => _loadLinkBandwidth(d), 250);
}

function _positionLinkTip(e) {
  if (!linkTip) return;
  const W = window.innerWidth, H = window.innerHeight;
  let left = e.pageX + 16, top = e.pageY - 10;
  if (left + 300 > W) left = e.pageX - 300 - 6;
  if (top  + 200 > H) top  = H - 200;
  linkTip.style.left = left + 'px';
  linkTip.style.top  = top  + 'px';
}

async function _loadLinkBandwidth(d) {
  const bwEl = document.getElementById('link-bw-section');
  if (!bwEl) return;
  const ifIds = [d.src_interface_id, d.dst_interface_id].filter(Boolean);
  if (!ifIds.length) { bwEl.textContent = 'Pas d\'interface trouvée'; return; }
  try {
    const metrics = await sql(
      `SELECT interface_id::text AS interface_id, time, in_octets, out_octets,
              in_bps, out_bps, in_errors, out_errors
       FROM interface_metrics_history
       WHERE interface_id = ANY($1::uuid[])
       ORDER BY time DESC LIMIT 6`,
      [ifIds]
    ).catch(() => []);

    if (!metrics.length) { bwEl.textContent = 'Pas de métriques disponibles'; return; }

    const byIf = {};
    metrics.forEach(m => { if (!byIf[m.interface_id]) byIf[m.interface_id] = []; byIf[m.interface_id].push(m); });

    const rows = Object.entries(byIf).map(([ifId, samples]) => {
      let inBps = samples[0]?.in_bps, outBps = samples[0]?.out_bps;
      if ((inBps == null || inBps === 0) && samples.length >= 2) {
        const t1 = new Date(samples[0].time), t0 = new Date(samples[1].time);
        const dt = (t1 - t0) / 1000;
        if (dt > 0) {
          const dIn  = (samples[0].in_octets  || 0) - (samples[1].in_octets  || 0);
          const dOut = (samples[0].out_octets || 0) - (samples[1].out_octets || 0);
          if (dIn  >= 0) inBps  = Math.round(dIn  / dt * 8);
          if (dOut >= 0) outBps = Math.round(dOut / dt * 8);
        }
      }
      return { ifId, inBps: inBps || 0, outBps: outBps || 0, inErr: samples[0]?.in_errors || 0, outErr: samples[0]?.out_errors || 0 };
    });

    const ifSpeeds = await sql(
      `SELECT id::text AS id, speed, name FROM interfaces WHERE id = ANY($1::uuid[])`,
      [ifIds]
    ).catch(() => []);
    const speedById = Object.fromEntries(ifSpeeds.map(i => [i.id, { speed: i.speed || 1e9, name: i.name }]));

    const color = pct => pct < 50 ? '#22c55e' : pct < 80 ? '#f97316' : '#ef4444';
    const bwHtml = rows.map(r => {
      const maxBps  = speedById[r.ifId]?.speed || 1e9;
      const ifName  = speedById[r.ifId]?.name  || ('IF ' + r.ifId);
      const inPct   = Math.min(100, maxBps > 0 ? (r.inBps  / maxBps) * 100 : 0);
      const outPct  = Math.min(100, maxBps > 0 ? (r.outBps / maxBps) * 100 : 0);
      return `<div style="margin-bottom:8px">
        <div style="font-size:9px;color:#60a5fa;font-weight:700;margin-bottom:3px">${esc(ifName)}</div>
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:3px">
          <span style="width:22px;font-size:9px;color:#94a3b8">↓ IN</span>
          <div class="bw-bar-wrap"><div class="bw-bar-inner" style="width:${inPct.toFixed(1)}%;background:${color(inPct)}"></div></div>
          <span style="font-size:10px;font-family:monospace;width:58px;text-align:right;color:#e2e8f0">${bpsH(r.inBps)}</span>
        </div>
        <div style="display:flex;align-items:center;gap:6px">
          <span style="width:22px;font-size:9px;color:#94a3b8">↑ OUT</span>
          <div class="bw-bar-wrap"><div class="bw-bar-inner" style="width:${outPct.toFixed(1)}%;background:${color(outPct)}"></div></div>
          <span style="font-size:10px;font-family:monospace;width:58px;text-align:right;color:#e2e8f0">${bpsH(r.outBps)}</span>
        </div>
        ${(r.inErr || r.outErr) ? `<div style="font-size:9px;color:#ef4444;margin-top:2px">⚠ Err: ↓${r.inErr} ↑${r.outErr}</div>` : ''}
      </div>`;
    }).join('');

    bwEl.innerHTML = `<div style="color:#60a5fa;font-size:9px;font-weight:700;margin-bottom:5px;text-transform:uppercase;letter-spacing:.5px">Bande passante</div>${bwHtml}`;
  } catch (e) { if (bwEl) bwEl.textContent = 'Erreur chargement'; }
}

function hideLinkTooltip() {
  if (linkTip) linkTip.style.display = 'none';
  clearTimeout(_linkTimer);
}

/* ════════════════════════════════════════════════════════
   POPUP DEVICE
════════════════════════════════════════════════════════ */
document.querySelectorAll('.popup-tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.popup-tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.popup-tab-pane').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('ptab-' + btn.dataset.ptab).classList.add('active');
  });
});

let _currentPopupNode = null;

document.getElementById('popup-lock-btn').addEventListener('click', () => {
  if (!_currentPopupNode) return;
  const d = _currentPopupNode, btn = document.getElementById('popup-lock-btn');
  d._unlocked = !d._unlocked;
  if (d._unlocked) {
    d.fx = null; d.fy = null;
    btn.textContent = '🔓 Verrouiller'; btn.classList.add('unlocked');
    state.simulation?.alpha(0.2).restart();
    toast('Nœud déverrouillé — déplacez-le');
  } else {
    d.fx = d.x; d.fy = d.y;
    btn.textContent = '🔒 Déplacer'; btn.classList.remove('unlocked');
    toast('Nœud verrouillé');
  }
});

const _charts = {};
function _destroyChart(id) { if (_charts[id]) { _charts[id].destroy(); delete _charts[id]; } }
function _makeChart(id, labels, data, color, label, yMax) {
  _destroyChart(id);
  const ctx = document.getElementById(id)?.getContext('2d');
  if (!ctx) return;
  _charts[id] = new Chart(ctx, {
    type: 'line',
    data: { labels, datasets: [{ label, data, borderColor: color, backgroundColor: color + '18', fill: true, tension: 0.3, pointRadius: 0, pointHoverRadius: 3, borderWidth: 2 }] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { display: false },
        y: { min: 0, max: yMax, ticks: { color: '#5a9090', font: { size: 9 } }, grid: { color: 'rgba(0,128,128,0.08)' }, border: { color: 'var(--border)' } },
      },
    },
  });
}

async function showNodePopup(node) {
  _currentPopupNode = node;
  const d = node.data;
  document.querySelectorAll('.popup-tab-btn').forEach(b => b.classList.toggle('active', b.dataset.ptab === 'info'));
  document.querySelectorAll('.popup-tab-pane').forEach(p => p.classList.toggle('active', p.id === 'ptab-info'));

  document.getElementById('popup-icon').innerHTML = `<i class="fas ${FA_ICONS[d.type] || FA_ICONS.unknown}"></i>`;
  document.getElementById('popup-hostname').textContent = d.hostname;
  document.getElementById('popup-ip-badge').textContent = d.ip || 'IP inconnue';

  const sLabel = d.status === 'online' ? 'En ligne' : d.status === 'offline' ? 'Hors ligne' : 'Inconnu';
  const sBadge = document.getElementById('popup-status-badge');
  sBadge.textContent = sLabel; sBadge.className = 'popup-badge ' + d.status;
  document.getElementById('popup-type-badge').textContent = d.category_name || d.type || 'Inconnu';

  const lockBtn = document.getElementById('popup-lock-btn');
  lockBtn.textContent = node._unlocked ? '🔓 Verrouiller' : '🔒 Déplacer';
  lockBtn.classList.toggle('unlocked', !!node._unlocked);
  document.getElementById('node-popup').classList.add('visible');

  const statusColor = STATUS_COLORS[d.status] || '#555';
  let html = `<div class="popup-row"><span class="popup-key">Statut</span><span class="popup-val popup-status"><span style="width:6px;height:6px;border-radius:50%;background:${statusColor};box-shadow:0 0 4px ${statusColor};display:inline-block;margin-right:4px"></span>${sLabel}</span></div>`;
  html += row('IP Mgmt', d.ip, true);
  html += row('Vendor', d.vendor);
  html += row('Famille', d.family_name);
  html += row('Modèle', d.model);
  html += row('Firmware', d.firmware);
  html += row('N° Série', d.serial_number, true);
  html += row('Localisation', d.location);
  html += row('Contact', d.snmp_contact);
  html += row('Uptime', fmtUptime(d.uptime));
  if (d.last_poll) html += row('Dernier poll', new Date(d.last_poll).toLocaleString('fr-FR'));
  document.getElementById('ptab-info').innerHTML = html;

  let snmpHtml = '';
  if (d.snmp_description) snmpHtml += `<div class="popup-section">sysDescr</div><div style="font-size:10px;color:var(--text3);line-height:1.6;font-family:var(--font);word-break:break-all;background:var(--surface2);padding:8px;border-radius:6px">${esc(d.snmp_description)}</div>`;
  if (d.sysobject_oid) snmpHtml += row('sysObjectID', d.sysobject_oid, true);
  snmpHtml += row('ICMP', d.icmp_status);
  snmpHtml += row('SNMP', d.snmp_status);
  document.getElementById('ptab-snmp').innerHTML = snmpHtml || '<div style="color:var(--text3);font-size:12px">Pas de données SNMP</div>';

  document.getElementById('ptab-interfaces').innerHTML = '<div style="color:var(--text3);font-size:12px;padding:10px">Chargement…</div>';
  document.getElementById('ptab-metrics').innerHTML    = '<div style="color:var(--text3);font-size:12px;padding:10px">Chargement…</div>';
  _loadPopupInterfaces(d.id);
  _loadPopupMetrics(d.id);
}

async function _loadPopupInterfaces(deviceId) {
  try {
    const ifaces = await sql(
      `SELECT i.id::text, i.name, i.description, i.type, i.speed, i.mac_address,
              ist.admin_status, ist.oper_status, ist.last_change
       FROM interfaces i
       LEFT JOIN LATERAL (
           SELECT admin_status, oper_status, last_change
           FROM interfaces_status
           WHERE interface_id = i.id
           ORDER BY last_change DESC
           LIMIT 1
       ) ist ON TRUE
       WHERE i.device_id = $1::uuid
       ORDER BY i.name`,
      [deviceId]
    );
    if (!ifaces.length) {
      document.getElementById('ptab-interfaces').innerHTML = '<div style="color:var(--text3);font-size:12px">Aucune interface</div>';
      return;
    }
    let html = `<div style="font-size:10px;color:var(--text3);margin-bottom:8px">${ifaces.length} interface(s)</div>`;
    ifaces.forEach(i => {
      const op  = i.oper_status  || 'Unknown';
      const adm = i.admin_status || '—';
      const up = op === 'Up', down = op === 'Down';
      const dotColor = up ? 'var(--green)' : down ? 'var(--red)' : 'var(--text3)';
      const stClass  = up ? 'iface-up' : down ? 'iface-down' : 'iface-unknown';
      html += `<div class="iface-row">
        <div class="iface-dot" style="background:${dotColor};${up ? 'box-shadow:0 0 4px ' + dotColor : ''}"></div>
        <div class="iface-name" title="${esc(i.name)}">${esc(i.name)}</div>
        <div class="iface-desc">${esc(i.description || '')}</div>
        <div class="iface-speed">${bpsH(i.speed)}</div>
        <div class="iface-status ${stClass}">${op} / ${adm}</div>
      </div>`;
    });
    document.getElementById('ptab-interfaces').innerHTML = html;
  } catch (e) {
    document.getElementById('ptab-interfaces').innerHTML = `<div style="color:var(--red);font-size:12px">Erreur: ${esc(e.message)}</div>`;
  }
}

async function _loadPopupMetrics(deviceId) {
  try {
    const metrics = await sql(
      `SELECT time, cpu_load, ram_usage, icmp_rtt, icmp_loss
       FROM device_metrics_history
       WHERE device_id = $1::uuid
       ORDER BY time DESC LIMIT 60`,
      [deviceId]
    );
    const el = document.getElementById('ptab-metrics');
    if (!metrics.length) { el.innerHTML = '<div style="color:var(--text3);font-size:12px">Pas encore de métriques</div>'; return; }

    const m   = [...metrics].reverse();
    const lbl = m.map(r => new Date(r.time).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }));
    const last = m[m.length - 1];

    el.innerHTML = `
      <div class="metrics-grid">
        <div class="metric-card"><div class="metric-label">CPU</div><div class="metric-current">${last?.cpu_load ?? '—'}<span>%</span></div><div class="metric-chart-wrap"><canvas id="chart-cpu"></canvas></div></div>
        <div class="metric-card"><div class="metric-label">RAM</div><div class="metric-current">${last?.ram_usage ?? '—'}<span>%</span></div><div class="metric-chart-wrap"><canvas id="chart-ram"></canvas></div></div>
      </div>
      <div style="margin-top:12px">
        <div class="metric-card">
          <div class="metric-label">RTT / Perte paquets</div>
          <div style="display:flex;gap:16px;margin-bottom:6px">
            <span class="metric-current" style="font-size:14px">${last?.icmp_rtt ? last.icmp_rtt.toFixed(1) : '—'}<span> ms</span></span>
            <span class="metric-current" style="font-size:14px;color:${(last?.icmp_loss || 0) > 0 ? 'var(--red)' : 'var(--green)'}">${last?.icmp_loss ?? '—'}<span> % perte</span></span>
          </div>
          <div class="metric-chart-wrap"><canvas id="chart-rtt"></canvas></div>
        </div>
      </div>`;
    _makeChart('chart-cpu', lbl, m.map(r => r.cpu_load),  '#008080', 'CPU %', 100);
    _makeChart('chart-ram', lbl, m.map(r => r.ram_usage), '#005959', 'RAM %', 100);
    _makeChart('chart-rtt', lbl, m.map(r => r.icmp_rtt),  '#16a34a', 'RTT ms', undefined);
    if (_charts['chart-rtt']) { _charts['chart-rtt'].options.scales.y.max = undefined; _charts['chart-rtt'].update(); }
  } catch (e) {
    document.getElementById('ptab-metrics').innerHTML = `<div style="color:var(--red);font-size:12px">Erreur: ${esc(e.message)}</div>`;
  }
}

function closeNodePopup() {
  document.getElementById('node-popup').classList.remove('visible');
  _currentPopupNode = null;
  ['chart-cpu', 'chart-ram', 'chart-rtt'].forEach(_destroyChart);
}
document.getElementById('popup-close').addEventListener('click', closeNodePopup);

/* ════════════════════════════════════════════════════════
   TOOLBAR
════════════════════════════════════════════════════════ */
document.getElementById('btn-fit').addEventListener('click', fitGraph);
document.getElementById('btn-refresh').addEventListener('click', refreshMap);
document.getElementById('btn-export').addEventListener('click', exportSVG);
document.getElementById('btn-path-mode').addEventListener('click', togglePathMode);
document.getElementById('btn-layout').addEventListener('change', function () { applyLayout(this.value); });

document.getElementById('btn-toggle-labels').addEventListener('click', function () {
  state.showLabels = !state.showLabels;
  this.classList.toggle('active', state.showLabels);
  g.selectAll('.node-label').attr('display', state.showLabels ? null : 'none');
});

document.getElementById('btn-toggle-ports').addEventListener('click', function () {
  state.showPorts = !state.showPorts;
  this.classList.toggle('active', state.showPorts);
  g.selectAll('.port-label-g').attr('display', state.showPorts ? null : 'none');
});

document.getElementById('btn-save-pos').addEventListener('click', async () => {
  if (!state.currentMap) { toast('Aucune carte active', 'error'); return; }
  loading(true, 'Mémorisation des positions…');
  try {
    for (const n of state.graphNodes) {
      await exec(
        `UPDATE map_devices SET pos_x = $1, pos_y = $2, is_pinned = TRUE
         WHERE map_id = $3 AND device_id = $4::uuid`,
        [Math.round(n.x || 0), Math.round(n.y || 0), state.currentMap.id, n.id]
      );
    }
    toast('Positions mémorisées !', 'success');
  } catch (e) { toast('Erreur: ' + e.message, 'error'); }
  finally { loading(false); }
});

document.getElementById('btn-apply-styles').addEventListener('click', () => { loadStyles(); toast('Styles appliqués', 'success'); });
document.getElementById('btn-apply-sim').addEventListener('click', () => {
  if (!state.simulation) return;
  state.simulation
    .force('charge', d3.forceManyBody().strength(+document.getElementById('sim-strength').value))
    .force('link',   d3.forceLink(state.graphLinks).id(d => d.id).distance(+document.getElementById('sim-distance').value))
    .alpha(0.5).restart();
});

document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'f') { e.preventDefault(); document.getElementById('canvas-search').focus(); }
  if (e.key === 'Escape') {
    if (state.pathMode) { togglePathMode(); return; }
    document.getElementById('canvas-search').value = '';
    g.selectAll('.node-group').attr('opacity', null);
    closeNodePopup();
  }
});

/* ════════════════════════════════════════════════════════
   STYLES
════════════════════════════════════════════════════════ */
async function loadStyles() {
  const [media, thick, status] = await Promise.all([
    sql(`SELECT link_type, base_color, dash_array FROM map_style_media ORDER BY link_type`).catch(() => []),
    sql(`SELECT name, min_bps, max_bps, thickness_px FROM map_style_thickness ORDER BY min_bps`).catch(() => []),
    sql(`SELECT metric_type, color FROM map_status ORDER BY metric_type`).catch(() => []),
  ]);
  state.styleMedia = Object.fromEntries(media.map(m => [m.link_type, m]));

  document.getElementById('style-media-list').innerHTML = media.map(m =>
    `<div style="display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid var(--border)">
      <div style="width:36px;height:3px;background:${m.base_color};border-radius:2px"></div>
      <span style="font-size:12px;color:var(--text2)">${m.link_type}</span>
      <code style="margin-left:auto;font-size:10px;color:var(--text3)">${m.base_color}</code>
    </div>`
  ).join('') || '<div style="color:var(--text3);font-size:12px">Aucune donnée</div>';

  document.getElementById('style-thickness-list').innerHTML = thick.map(t =>
    `<div style="display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid var(--border)">
      <div style="width:36px;height:${t.thickness_px}px;background:var(--border2);border-radius:2px"></div>
      <span style="font-size:12px;color:var(--text2)">${t.name}</span>
    </div>`
  ).join('') || '<div style="color:var(--text3);font-size:12px">Aucune donnée</div>';

  document.getElementById('style-status-list').innerHTML = status.map(s =>
    `<div style="display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid var(--border)">
      <div style="width:10px;height:10px;border-radius:50%;background:${s.color}"></div>
      <span style="font-size:12px;color:var(--text2)">${s.metric_type}</span>
    </div>`
  ).join('') || '<div style="color:var(--text3);font-size:12px">Aucune donnée</div>';

  document.getElementById('legend-content').innerHTML = media.slice(0, 6).map(m =>
    `<div class="legend-row">
      <div class="legend-line" style="background:${m.base_color}${m.dash_array ? ';background:none;border-top:2px dashed ' + m.base_color : ''}"></div>
      <span>${m.link_type}</span>
    </div>`
  ).join('');

  applyStyles();
}

function applyStyles() {
  if (!state.graphLinks.length) return;
  g.selectAll('.link-line').each(function (d) {
    const style = state.styleMedia[d.link_type];
    const color = style?.base_color || linkColor(d.link_type);
    const dash  = style?.dash_array || null;
    d3.select(this).attr('stroke', color).attr('stroke-dasharray', dash);
    d.color = color; d.dash = dash;
  });
}

/* ════════════════════════════════════════════════════════
   FILTRES CATÉGORIES
════════════════════════════════════════════════════════ */
function buildFilterBar() {
  const cats = [...new Set(state.allDevices.map(d => d.type).filter(Boolean))];
  const LABELS = { switch: 'Switch', router: 'Routeur', firewall: 'Firewall', wlc: 'WLC', ap: 'AP', server: 'Serveur', ups: 'UPS', printer: 'Imprimante', unknown: 'Inconnu' };
  const bar = document.getElementById('filter-bar');
  bar.innerHTML = '';
  cats.forEach(slug => {
    const chip = document.createElement('button');
    chip.className = 'filter-chip';
    chip.dataset.slug = slug;
    chip.innerHTML = `<i class="fas ${FA_ICONS[slug] || FA_ICONS.unknown}" style="font-size:9px"></i> ${LABELS[slug] || slug}`;
    chip.addEventListener('click', () => {
      chip.classList.toggle('active');
      if (state.activeFilters.has(slug)) state.activeFilters.delete(slug);
      else state.activeFilters.add(slug);
      applyNodeFilter();
    });
    bar.appendChild(chip);
  });
}

function applyNodeFilter() {
  const hide = state.activeFilters.size > 0;
  g.selectAll('.node-group').each(function (d) {
    d3.select(this).attr('display', (!hide || state.activeFilters.has(d.type)) ? null : 'none');
  });
  g.selectAll('.link-line').each(function (d) {
    const ok = !hide || (state.activeFilters.has(d.source.type || '') && state.activeFilters.has(d.target.type || ''));
    d3.select(this).attr('display', ok ? null : 'none');
  });
}

/* ════════════════════════════════════════════════════════
   RECHERCHE CANVAS
════════════════════════════════════════════════════════ */
function initCanvasSearch() {
  const inp = document.getElementById('canvas-search');
  inp.addEventListener('input', () => {
    const q = inp.value.trim().toLowerCase();
    if (!q) { g.selectAll('.node-group').attr('opacity', null); return; }
    g.selectAll('.node-group').each(function (d) {
      const match = d.label.toLowerCase().includes(q) || (d.ip || '').includes(q);
      d3.select(this).attr('opacity', match ? 1 : 0.1);
    });
  });
  inp.addEventListener('keydown', e => {
    if (e.key !== 'Enter') return;
    const q = inp.value.trim().toLowerCase();
    if (!q) return;
    const found = state.graphNodes.find(n => n.label.toLowerCase().includes(q) || (n.ip || '').includes(q));
    if (found && found.x != null) {
      const W = document.getElementById('map-area').clientWidth;
      const H = document.getElementById('map-area').clientHeight;
      svg.transition().duration(500).call(_zoomHandler.transform, d3.zoomIdentity.translate(W / 2 - found.x * 1.5, H / 2 - found.y * 1.5).scale(1.5));
    }
  });
  document.getElementById('btn-search-clear').addEventListener('click', () => {
    inp.value = '';
    g.selectAll('.node-group').attr('opacity', null);
    inp.focus();
  });
}

/* ════════════════════════════════════════════════════════
   MODE CHEMIN
════════════════════════════════════════════════════════ */
function togglePathMode() {
  state.pathMode = !state.pathMode;
  state.pathNodes = [];
  document.getElementById('btn-path-mode').classList.toggle('active', state.pathMode);
  document.getElementById('path-mode-bar').classList.toggle('active', state.pathMode);
  if (!state.pathMode) clearPathHighlight();
  else document.getElementById('path-status').textContent = 'Cliquez sur un premier nœud…';
}

function handlePathClick(node) {
  state.pathNodes.push(node);
  if (state.pathNodes.length === 1) {
    document.getElementById('path-status').textContent = `${node.label} → Cliquez sur la destination…`;
    g.selectAll('.node-group').attr('opacity', d => d.id === node.id ? 1 : 0.4);
  } else if (state.pathNodes.length === 2) {
    const [a, b] = state.pathNodes;
    const path = findPath(a.id, b.id);
    document.getElementById('path-status').textContent = path
      ? `${a.label} → ${b.label} : ${path.length - 1} saut(s)`
      : 'Aucun chemin trouvé';
    highlightPath(path);
    state.pathNodes = [];
  }
}

function findPath(srcId, dstId) {
  const adj = {};
  state.graphNodes.forEach(n => { adj[n.id] = []; });
  state.graphLinks.forEach(l => {
    const s = l.source.id || l.source, t = l.target.id || l.target;
    if (adj[s]) adj[s].push(t);
    if (adj[t]) adj[t].push(s);
  });
  const visited = new Set(), queue = [[srcId]];
  while (queue.length) {
    const path = queue.shift(), cur = path[path.length - 1];
    if (cur === dstId) return path;
    if (visited.has(cur)) continue;
    visited.add(cur);
    for (const nb of (adj[cur] || [])) { if (!visited.has(nb)) queue.push([...path, nb]); }
  }
  return null;
}

function highlightPath(path) {
  clearPathHighlight();
  if (!path) { g.selectAll('.node-group').attr('opacity', null); return; }
  const pathSet = new Set(path);
  const pathPairs = new Set();
  for (let i = 0; i < path.length - 1; i++) pathPairs.add([path[i], path[i + 1]].sort().join('|'));
  g.selectAll('.node-group').each(function (d) {
    d3.select(this).classed('path-highlight', pathSet.has(d.id)).classed('path-dim', !pathSet.has(d.id)).attr('opacity', null);
  });
  g.selectAll('.link-line').each(function (d) {
    const s = d.source.id || d.source, t = d.target.id || d.target;
    const on = pathPairs.has([s, t].sort().join('|'));
    d3.select(this).classed('path-highlight', on).classed('path-dim', !on);
  });
}

function clearPathHighlight() {
  g.selectAll('.node-group').classed('path-highlight', false).classed('path-dim', false).attr('opacity', null);
  g.selectAll('.link-line').classed('path-highlight', false).classed('path-dim', false);
}

document.getElementById('btn-path-clear').addEventListener('click', () => {
  state.pathMode = false; state.pathNodes = [];
  document.getElementById('btn-path-mode').classList.remove('active');
  document.getElementById('path-mode-bar').classList.remove('active');
  clearPathHighlight();
});

/* ════════════════════════════════════════════════════════
   EXPORT SVG
════════════════════════════════════════════════════════ */
function exportSVG() {
  const svgEl = document.getElementById('map-svg');
  const clone = svgEl.cloneNode(true);
  const W = svgEl.clientWidth, H = svgEl.clientHeight;
  clone.setAttribute('width', W); clone.setAttribute('height', H);
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');

  const style = document.createElementNS('http://www.w3.org/2000/svg', 'style');
  style.textContent = `
    * { font-family: system-ui, sans-serif; }
    rect { fill: #f0f6f6; }
    .node-bg { stroke-width: 2.5; }
    .node-label { font-size: 11px; fill: #2d6060; }
    .link-line { stroke-linecap: round; }
    .link-label { font-size: 9px; fill: #5a9090; }`;
  clone.insertBefore(style, clone.firstChild);

  const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  bg.setAttribute('width', W); bg.setAttribute('height', H); bg.setAttribute('fill', '#f0f6f6');
  clone.insertBefore(bg, clone.querySelector('#map-g'));

  const FA_UNICODE = {
    'fa-network-wired': '⎋', 'fa-random': '⇄', 'fa-shield-alt': '⊠', 'fa-wifi': '⊛',
    'fa-broadcast-tower': '◎', 'fa-server': '▣', 'fa-battery-half': '▤', 'fa-print': '✇', 'fa-question-circle': '◇',
  };
  clone.querySelectorAll('foreignObject').forEach(fo => {
    const parent = fo.parentNode;
    const iEl = fo.querySelector('i');
    const cls = iEl ? [...iEl.classList].find(c => c.startsWith('fa-')) : 'fa-question-circle';
    const color = iEl?.style?.color || '#008080';
    const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    txt.setAttribute('x', '0'); txt.setAttribute('y', '5');
    txt.setAttribute('text-anchor', 'middle'); txt.setAttribute('dominant-baseline', 'middle');
    txt.setAttribute('font-size', '14'); txt.setAttribute('fill', color);
    txt.textContent = FA_UNICODE[cls] || '◇';
    parent.replaceChild(txt, fo);
  });

  const cssVars = {
    '--green': '#16a34a', '--red': '#dc2626', '--text3': '#5a9090', '--text2': '#2d6060',
    '--duck': '#008080', '--duck2': '#009999', '--duck3': '#006666',
    '--border': '#c8e0e0', '--surface2': '#f4fafa', '--surface3': '#e8f5f5',
  };
  clone.querySelectorAll('[style]').forEach(el => {
    let s = el.getAttribute('style');
    Object.entries(cssVars).forEach(([k, v]) => {
      s = s.replace(new RegExp('var\\(\\s*' + k.replace(/[-]/g, '\\$&') + '\\s*\\)', 'g'), v);
    });
    el.setAttribute('style', s);
  });

  const svgData = '<?xml version="1.0" encoding="UTF-8"?>\n' + new XMLSerializer().serializeToString(clone);
  const blob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.download = (state.currentMap?.name || 'carte') + '.svg';
  a.href = url; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast('Export SVG téléchargé', 'success');
}

/* ════════════════════════════════════════════════════════
   LAYOUTS
════════════════════════════════════════════════════════ */
function applyLayout(type) {
  if (!state.graphNodes.length) return;
  const W = document.getElementById('map-area').clientWidth;
  const H = document.getElementById('map-area').clientHeight;

  if (type === 'force') {
    state.graphNodes.forEach(n => { n.fx = null; n.fy = null; });
    state.simulation?.alpha(0.8).restart();
    setTimeout(() => { state.graphNodes.forEach(n => { n.fx = n.x; n.fy = n.y; }); }, 3000);
    return;
  }
  if (type === 'radial') {
    const byCat = {};
    state.graphNodes.forEach(n => { const c = n.type || 'unknown'; if (!byCat[c]) byCat[c] = []; byCat[c].push(n); });
    const cats = Object.keys(byCat), step = Math.min(W, H) / (cats.length + 1) / 2;
    cats.forEach((cat, ci) => {
      const r = step * (ci + 1), nodes = byCat[cat];
      nodes.forEach((n, ni) => { const a = (2 * Math.PI * ni) / nodes.length; n.fx = W / 2 + r * Math.cos(a); n.fy = H / 2 + r * Math.sin(a); });
    });
  }
  if (type === 'tree') {
    const ORDER = { firewall: 0, router: 1, wlc: 2, switch: 3, ap: 4, server: 5, unknown: 6 };
    const levels = {};
    state.graphNodes.forEach(n => { const l = ORDER[n.type ?? 'unknown'] ?? 6; if (!levels[l]) levels[l] = []; levels[l].push(n); });
    const keys = Object.keys(levels).map(Number).sort((a, b) => a - b);
    const yStep = H / (keys.length + 1);
    keys.forEach((lvl, li) => {
      const ns = levels[lvl], xStep = W / (ns.length + 1);
      ns.forEach((n, ni) => { n.fx = xStep * (ni + 1); n.fy = yStep * (li + 1); });
    });
  }
  state.simulation?.alpha(0.01).restart();
  setTimeout(() => { state.simulation?.stop(); fitGraph(); }, 300);
}

/* ════════════════════════════════════════════════════════
   REFRESH
════════════════════════════════════════════════════════ */
async function refreshMap() {
  if (!state.currentMap) { toast('Aucune carte active', 'error'); return; }
  loading(true, 'Rafraîchissement…');
  try {
    await loadAllDevices();
    await loadMap(state.currentMap.id);
    state.lastRefresh = new Date();
    toast('Carte rafraîchie', 'success');
  } catch (e) { toast('Erreur refresh: ' + e.message, 'error'); }
  finally { loading(false); }
}

/* ════════════════════════════════════════════════════════
   DÉMARRAGE
════════════════════════════════════════════════════════ */
init().then(() => { loadStyles(); initCanvasSearch(); });