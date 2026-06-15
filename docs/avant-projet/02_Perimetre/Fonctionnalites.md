# Fonctionnalités attendues

## Table des matières
1. [Découverte & inventaire](#découverte--inventaire)
2. [Topologie & visualisation](#topologie--visualisation)
3. [Supervision & alerting](#supervision--alerting)
4. [Administration & maintenance](#administration--maintenance)
5. [Intégration & export](#intégration--export)
6. [Exigences non fonctionnelles](#exigences-non-fonctionnelles)

---

# Découverte & inventaire
- Découverte active : ICMP, scan de ports, SNMP v2c/3, SSH, API HTTP(S), LLDP/CDP, ARP.
- Inventaire détaillé : modèle, version firmware, interfaces, IP, VLANs, rôle.
- Classification automatique : vendor, type, rôle.

---

# Topologie & visualisation
- Carte interactive : zoom, filtres, recherche.
- Visuel parlant : Etterchannel, STP, charge.
- Analyse d’impact : dépendances et redondances.
- Historique simplifié des changements.

---

# Supervision & alerting
- Alertes temps réel : panne, interfaces down, traps SNMP.
- Notifications : email, webhook.
- Journalisation et audit des actions.

---

# Administration & maintenance
- Accès à distance : SSH/HTTPS.
- Sauvegarde/restauration configurations.
- Comparaison et application de templates.
- Mise à jour/patch d’équipements.
- Gestion des droits (RBAC).

---

# Intégration & export
- API REST : inventaire, topologie, événements.
- Connecteurs CSV/JSON, intégration CMDB.
- Export visuel : PNG, PDF, SVG, Visio.

---

# Exigences non fonctionnelles
- Sécurité : TLS, chiffrement, audit.
- Scalabilité : gérer centaines d’équipements.
- Non-intrusif : scans configurables, throttling.
- Disponibilité et sauvegarde régulière.