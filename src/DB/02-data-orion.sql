-- --------------------------------------------------------
-- 1. VENDORS (Constructeurs)
-- --------------------------------------------------------
INSERT INTO vendors (name, slug) VALUES 
('Cisco Systems', 'cisco'),
('Dell Technologies', 'dell'),
('VMware', 'vmware'),
('Linux Generic', 'linux');

-- --------------------------------------------------------
-- 2. VENDOR IANA PEN (SNMP ID)
-- --------------------------------------------------------
-- On utilise des sous-requêtes pour récupérer les ID générés dynamiquement
INSERT INTO vendor_iana_pen (vendor_id, pen) VALUES 
((SELECT id FROM vendors WHERE slug='cisco'), 9),
((SELECT id FROM vendors WHERE slug='dell'), 674),
((SELECT id FROM vendors WHERE slug='vmware'), 6876),
((SELECT id FROM vendors WHERE slug='linux'), 8072); -- Net-SNMP

-- --------------------------------------------------------
-- 3. VENDOR OUI (MAC Prefixes - Échantillon)
-- --------------------------------------------------------
INSERT INTO vendor_oui (vendor_id, mac_prefix) VALUES 
((SELECT id FROM vendors WHERE slug='cisco'), '00000C'),
((SELECT id FROM vendors WHERE slug='cisco'), '005056'),
((SELECT id FROM vendors WHERE slug='cisco'), '0022BD'),
((SELECT id FROM vendors WHERE slug='dell'), '001422'),
((SELECT id FROM vendors WHERE slug='vmware'), '000569');

-- --------------------------------------------------------
-- 4. DEVICE CATEGORIES
-- --------------------------------------------------------
INSERT INTO device_categories (slug, name, icon_class) VALUES 
('switch', 'Commutateur', 'fas fa-network-wired'),
('router', 'Routeur', 'fas fa-random'),
('firewall', 'Pare-Feu', 'fas fa-shield-alt'),
('wlc', 'Contrôleur Wi-Fi', 'fas fa-wifi'),
('ap', 'Point d''accès', 'fas fa-broadcast-tower'),
('server', 'Serveur', 'fas fa-server'),
('ups', 'Onduleur', 'fas fa-battery-half'),
('printer', 'Imprimante', 'fas fa-print');

-- --------------------------------------------------------
-- 5. DEVICE STATUS (Cycle de vie)
-- --------------------------------------------------------
INSERT INTO ref_device_status (code, name, color, is_monitored, description) VALUES 
('active', 'En Production', '#28a745', true, 'Équipement en service et supervisé'),
('maintenance', 'En Maintenance', '#fd7e14', true, 'En cours d''intervention, alertes silencieuses'),
('provisioning', 'En Installation', '#17a2b8', false, 'En cours de configuration, non supervisé'),
('stock', 'En Stock', '#6c757d', false, 'Dans le placard, éteint'),
('decom', 'Détruit ou réformé', '#343a40', false, 'Fin de vie, détruit ou réformé pour pièce');

-- --------------------------------------------------------
-- 6. MAP STYLE THICKNESS (Épaisseur selon débit)
-- --------------------------------------------------------
INSERT INTO map_style_thickness (name, min_bps, max_bps, thickness_px) VALUES 
('Low Speed (<100M)', 0, 100000000, 1),
('Fast Eth (100M)', 100000000, 1000000000, 2),
('Gigabit (1G)', 1000000000, 10000000000, 3),
('Ten Gig (10G)', 10000000000, 40000000000, 5),
('Backbone (>40G)', 40000000000, 999999999999, 8);

-- --------------------------------------------------------
-- 7. MAP STYLE MEDIA (Couleur selon support)
-- --------------------------------------------------------
INSERT INTO map_style_media (link_type, base_color, dash_array) VALUES 
('Copper', '#B87333', NULL),        -- Cuivre (Solid)
('Fiber', '#f1c40f', NULL),         -- Fibre (Solid - Jaune standard)
('Wireless', '#3498db', '5,5'),     -- Wi-Fi (Pointillés)
('Aggregate', '#9b59b6', NULL),     -- Etherchannel (Violet)
('Virtual', '#95a5a6', '2,2'),      -- VPN/Tunnel (Gris pointillés fins)
('Backplane', '#2c3e50', '10,2');   -- Stack Ring (Gris foncé)

-- --------------------------------------------------------
-- 8. MAP STATUS (Couleur selon état)
-- --------------------------------------------------------
INSERT INTO map_status (metric_type, color) VALUES 
('Up', '#2ecc71'),      -- Vert
('Down', '#e74c3c'),    -- Rouge
('Degraded', '#f39c12'); -- Orange

-- --------------------------------------------------------
-- 9. AUTH SNMP & PROFILES
-- --------------------------------------------------------

INSERT INTO auth_snmp (name, version, community) VALUES 
('Default Public', 'v2c', 'public'),   -- ID théorique: 1
('Default Private', 'v2c', 'private');  -- ID théorique: 2

INSERT INTO auth_profiles (name, snmp_id, cli_id) VALUES 
('Default Public Profile', (SELECT id FROM auth_snmp WHERE community='public' LIMIT 1), NULL),
('Default Private Profile', (SELECT id FROM auth_snmp WHERE community='private' LIMIT 1), NULL);

-- --------------------------------------------------------
-- 10. CATALOGUE DES PERMISSIONS
-- --------------------------------------------------------
INSERT INTO permissions (code, module, description) VALUES 
-- Inventory
('inventory.view', 'Inventory', 'Voir la liste des équipements'),
('inventory.create', 'Inventory', 'Ajouter un nouvel équipement'),
('inventory.edit', 'Inventory', 'Modifier les métadonnées'),
('inventory.delete', 'Inventory', 'Supprimer un équipement'),
('topology.view', 'Inventory', 'Visualiser les cartes'),
('topology.edit', 'Inventory', 'Modifier la topologie manuellement'),

-- Monitoring
('metrics.view', 'Monitoring', 'Voir les graphiques'),
('alerts.view', 'Monitoring', 'Voir le dashboard alertes'),
('alerts.ack', 'Monitoring', 'Acquitter une alerte'),
('alerts.configure', 'Monitoring', 'Modifier les seuils'),
('maintenance.schedule', 'Monitoring', 'Planifier une maintenance'),

-- NCM (Config)
('config.view', 'NCM', 'Lire les configurations'),
('config.diff', 'NCM', 'Comparer les versions'),
('config.download', 'NCM', 'Télécharger les fichiers'),
('config.backup_now', 'NCM', 'Forcer une sauvegarde'),
('config.restore', 'NCM', 'Restaurer une configuration'),
('compliance.audit', 'NCM', 'Lancer un audit de conformité'),

-- Automation
('terminal.open', 'Automation', 'Session Web-SSH Read-Only'),
('terminal.full_access', 'Automation', 'Session Web-SSH Enable/Root'),
('script.view', 'Automation', 'Voir les scripts'),
('script.edit', 'Automation', 'Modifier les scripts'),
('job.execute', 'Automation', 'Lancer une tâche de masse'),
('device.reboot', 'Automation', 'Redémarrer un équipement'),
('interface.toggle', 'Automation', 'Shut/No Shut interface'),

-- IPAM
('ipam.view', 'IPAM', 'Voir le plan d''adressage'),
('ipam.edit', 'IPAM', 'Gérer les sous-réseaux/VLANs'),
('dhcp.manage', 'IPAM', 'Gérer le DHCP'),

-- Security
('credentials.view_list', 'Security', 'Voir les noms de profils'),
('credentials.manage', 'Security', '[Haut Risque] Gérer les crédentials'),
('credentials.reveal', 'Security', '[Critique] Voir les mots de passe en clair'),
('audit.view', 'Security', 'Voir les logs d''audit'),
('security.port_security', 'Security', 'Clear port-security sticky'),

-- System
('admin.users', 'System', '[Critique] Gérer les utilisateurs'),
('admin.roles', 'System', '[Critique] Gérer les rôles ACL'),
('admin.ldap', 'System', '[Haut Risque] Configurer LDAP'),
('system.settings', 'System', '[Haut Risque] Configurer le NMS'),
('system.update', 'System', '[Critique] Mise à jour logiciel');

-- --------------------------------------------------------
-- 11. ROLES (Définitions abstraites)
-- --------------------------------------------------------
INSERT INTO roles (name, description, is_system) VALUES 
('Super Admin', 'Accès total système', TRUE),
('Operator', 'Opérations quotidiennes (Read-Write)', TRUE),
('Auditor', 'Consultation seule (Read-Only)', TRUE);

-- --------------------------------------------------------
-- 12. ROLE_PERMISSIONS (Mapping)
-- --------------------------------------------------------

-- A. Super Admin : A techniquement toutes les permissions, 
-- mais souvent géré via le flag 'is_super_admin' sur l'user directement.
-- On peuple quand même pour la forme si on enlève le flag.
INSERT INTO role_permissions (role_id, permission_id)
SELECT (SELECT id FROM roles WHERE name='Super Admin'), id FROM permissions;

-- B. Auditor : Uniquement les permissions *.view
INSERT INTO role_permissions (role_id, permission_id)
SELECT (SELECT id FROM roles WHERE name='Auditor'), id
FROM permissions
WHERE code LIKE '%.view%' OR code LIKE '%.view_list';

-- C. Operator : Le profil complexe
-- On insère tout ce qui n'est pas "Admin System", "Security Reveal" ou "Config Restore"
INSERT INTO role_permissions (role_id, permission_id)
SELECT (SELECT id FROM roles WHERE name='Operator'), id
FROM permissions
WHERE module IN ('Inventory', 'Monitoring', 'NCM', 'Automation', 'IPAM')
AND code NOT IN ('config.restore', 'script.edit', 'admin.users', 'admin.roles', 'system.update', 'credentials.reveal');

-- --------------------------------------------------------
-- 13. USERS & GROUPS (Données initiales)
-- --------------------------------------------------------

-- a. Groupes
INSERT INTO user_groups (name, slug, description, is_builtin) VALUES 
('Administrators', 'admins', 'Groupe racine', TRUE),
('Operators', 'operators', 'Opérateurs réseau', FALSE),
('Auditors', 'auditors', 'Auditeurs externes', FALSE);

-- b. Users (Mots de passe hashés "change_me" par défaut - À CHANGER RAPIDEMENT)
-- Note: Dans la réalité, le hash doit être généré par ton backend (Argon2/Bcrypt). 
-- Ici je mets une chaîne bidon pour l'exemple.
INSERT INTO app_users (username, email, is_super_admin) VALUES 
('admin', 'admin@local.nms', TRUE),
('operator', 'noc@local.nms', FALSE),
('auditor', 'audit@local.nms', FALSE);

-- c. Liaison User <-> Group
INSERT INTO user_group_members (user_id, group_id) VALUES 
((SELECT id FROM app_users WHERE username='admin'), (SELECT id FROM user_groups WHERE slug='admins')),
((SELECT id FROM app_users WHERE username='operator'), (SELECT id FROM user_groups WHERE slug='operators')),
((SELECT id FROM app_users WHERE username='auditor'), (SELECT id FROM user_groups WHERE slug='auditors'));



-- Admins Group -> Super Admin Role (Global)
INSERT INTO access_policies (policy_name, subject_id, role_id, scope_type) VALUES 
('Admin Policy', 
 (SELECT id FROM user_groups WHERE slug='admins'), 
 (SELECT id FROM roles WHERE name='Super Admin'), 
 'Global');

-- Operators Group -> Operator Role (Global)
INSERT INTO access_policies (policy_name, subject_id, role_id, scope_type) VALUES 
('Operator Global Access', 
 (SELECT id FROM user_groups WHERE slug='operators'), 
 (SELECT id FROM roles WHERE name='Operator'), 
 'Global');

-- Auditors Group -> Auditor Role (Global)
INSERT INTO access_policies (policy_name, subject_id, role_id, scope_type) VALUES 
('Audit Read-Only', 
 (SELECT id FROM user_groups WHERE slug='auditors'), 
 (SELECT id FROM roles WHERE name='Auditor'), 
 'Global');

-- --------------------------------------------------------
-- 15. MONITORING PROFIL
-- --------------------------------------------------------

INSERT INTO monitoring_profiles (name, scan_type, interval_seconds, timeout_ms, retry_count, is_enabled, description)
VALUES

-- ── ICMP ──────────────────────────────────────────────────────────
-- Ping léger toutes les 30 secondes pour détecter les pannes rapidement.
-- Alimente device_status.icmp_status + device_metrics_history.icmp_rtt/loss
(
    'ICMP_30s',
    'ICMP_Ping',
    30,      -- toutes les 30 secondes
    1500,    -- timeout 1.5s
    2,       -- 2 retry
    TRUE,
    'Ping de disponibilité toutes les 30s. Source principale des alertes up/down.'
),

-- ── SNMP Métriques ────────────────────────────────────────────────
-- Compteurs interfaces + CPU + RAM toutes les 5 minutes.
-- Alimente interface_metrics_history + device_metrics_history
(
    'SNMP_Metrics_5min',
    'SNMP_Metrics',
    300,     -- toutes les 5 minutes
    3000,    -- timeout 3s
    1,
    TRUE,
    'Métriques SNMP : CPU, RAM, compteurs interfaces (octets, erreurs, discards). '
    'Fréquence recommandée pour la supervision courante.'
),

-- ── SNMP Métriques haute fréquence ────────────────────────────────
-- Pour les liens critiques où on veut une granularité fine.
-- Désactivé par défaut, à activer manuellement sur les devices critiques.
(
    'SNMP_Metrics_1min',
    'SNMP_Metrics',
    60,
    3000,
    1,
    FALSE,
    'Métriques SNMP haute fréquence (1min). Désactivé par défaut — '
    'activer uniquement sur les équipements critiques (coeur de réseau).'
),

-- ── Topologie LLDP/CDP ────────────────────────────────────────────
-- Découverte des voisins + mise à jour network_links toutes les 10 min.
(
    'LLDP_10min',
    'LLDP_Topology',
    600,     -- toutes les 10 minutes
    4000,
    1,
    TRUE,
    'LLDP/CDP : mise à jour des voisins et des liens de cartographie. '
    'Détecte les changements de topologie (câbles débranchés, nouveaux switches).'
),

-- ── Scan complet (SNMP_Full) ──────────────────────────────────────
-- Rescan complet : interfaces, VLANs, trunks, EtherChannel, HSRP.
-- Toutes les heures pour mettre à jour la config des équipements.
(
    'SNMP_Full_1h',
    'SNMP_Full',
    3600,    -- toutes les heures
    5000,
    1,
    TRUE,
    'Rescan complet : interfaces, VLANs, trunks 802.1Q, EtherChannel/LACP, HSRP/VRRP. '
    'Met à jour la configuration des équipements découverts.'
),

-- ── Scan complet journalier ───────────────────────────────────────
-- Pour les environnements où un rescan horaire est trop fréquent.
-- Désactivé par défaut si SNMP_Full_1h est actif.
(
    'SNMP_Full_24h',
    'SNMP_Full',
    86400,   -- toutes les 24 heures
    5000,
    1,
    FALSE,
    'Rescan complet journalier. Alternative à SNMP_Full_1h pour les environnements stables.'
);