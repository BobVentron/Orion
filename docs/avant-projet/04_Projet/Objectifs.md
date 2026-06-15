# Objectifs et cadrages

**Version** : 1.0
**Date** : 2025-10-06
**Auteurs** : Alexis Lonjon

---

# But du projet
Le but du projet est de **réaliser une cartographie réseau automatique, fiable et exploitable** sur un périmètre restreint. Lors du PoC, le projet devra prouver que l'on peut :

- récupérer automatiquement des informations depuis des équipements réels ou virtuels ;
- stocker ces informations de façon structurée ;
- générer une topologie exploitable montrant les liaisons et dépendances basiques ;
- fournir une interface permettant d'explorer la cartographie, d'extraire des exports et de simuler un incident simple (ex : interface down) pour montrer l'analyse d'impact.

---

# Contexte et objectifs
- Montrer la valeur ajoutée d'une cartographie dynamique face à une documentation statique.
- Mettre en évidence l'importance de surveiller en temps réel son réseau.
- Permettre des actions d'administration et d'audit simplifiées sur l'ensemble du parc.
- Centraliser la récupération d'informations essentielles (version, statut ...) en vue d'une exploitation.

---

# Périmètre du projet

## In scope (obligatoire)
- Découverte et inventaire via : LLDP/CDP, SNMPv2c (lecture) et ICMP (ping) ; collecte minimale via SSH/API si disponible.
- Constitution d'une base d'inventaire (SQLite/JSON/MariaDB).
- Construction d'un graphe topologique simple (nœuds = équipements, liens = LLDP/ARP/ports connectés détectés).
- UI web simple permettant : l'affichage interactif (zoom/déplacement), la recherche par nom/IP, le filtrage par type.
- Export CSV / JSON des inventaires et de la topologie.
- Démonstration d'un scénario d'incident (interface down) et calcul d'impact basique.
- Documentation de déploiement et d'utilisation.

## Out of scope
- Système d'alerte complet et gestion d'événements.
- RBAC avancé / intégration SSO.
- Système de journalisation
- Historique des versions des fichiers de configuration
- Mises en place de script pour automatiser les actions
- Plannifier des tâches automatisé
- Sauvegarde/restore automatique des configurations et mise à jour des firmwares.
- Exportation vers des formats spécifiques (Visio/Draw.io)
- Haute disponibilité ou scalabilité à plusieurs milliers d'équipements.

---

# MVP — Fonctionnalités obligatoires pour le PoC

1. **Scan / découverte**
   - Entrée : liste d'adresses IP / plage ou liste d'hosts.
   - Méthodes : ICMP, SSH, SNMPv2c -> LLDP/CDP, ARP
   - Sortie : liste d'équipements détectés avec adresse IP, nom, vendor (si disponible), modèle, interfaces découvertes...
   - DoD : 80% des équipements du banc test détectés et renseignés au moins avec hostname/IP/interfaces.

2. **Inventaire stocké**
   - Stockage minimal : SQLite, JSON structuré, MariaDB.
   - Champs minimum : serial_number, hostname, management_ip, vendor, model, os_version, interfaces[{name, mac, ip, status}], last_seen.
   - DoD : export CSV/JSON contenant les champs ci-dessus.

3. **Génération de topologie**
   - Règles : préférer LLDP/CDP pour liaisons directes ; compléter par ARP/Tables CAM/ports si LLDP absent.
   - Visualisation : graph interactif (zoom/pan), affichage des attributs au survol.
   - DoD : topologie lisible et cohérente sur banc test (liens visibles entre switchs/hosts).

4. **Interface web minimale**
   - Pages : Dashboard (inventaire + statut), Carte topologique interactive, Page équipement (détails + actions basiques).
   - Actions : relancer un scan, export, recherche.
   - DoD : interface complète accessible localement.

5. **Scénario d'incident & analyse d'impact**
   - Simuler un port down (désactiver interface sur un device test) puis montrer : devices affectés et chemins alternatifs (s'il y en a).
   - DoD : démonstration reproductible durant la soutenance.

6. **Documentation & reproductibilité**
   - Documentaion avec les étapes pour installer l'outil et lancer un scan (prérequis, commandes, credentials de test).
   - DoD : un investisseur/client doit pouvoir lancer le PoC en < 30 minutes sur un poste.

---

# Fonctionnalités secondaires (si temps)
- Collecte SNMPv3 (auth + privacy).
- Stockage sécurisé des fichiers et des accès.
- Exports graphiques PNG/SVG de la topologie.
- Enrichissement automatique (récupération serial number, uptime, VLANs).

---

# Fonctionnalités non implémenter
- RBAC complet et SSO.
- Intégration Visio/format propriétaire.
- Tableau de bord métriques temps-réel (graphs par device).
- Sauvegarde automatique des configurations (via SSH + scp/tftp) pour quelques devices.
- Intégration d'un petit module d'alerting par webhook/email pour ping down.
- Interface d'édition manuelle de la topologie (pour corriger erreurs).
- Et toutes les autres fonctionnalités ...

---

# Architecture technique proposée

Composants principaux :

- **Scanner / Collector** : service Python qui exécute les scans ICMP/SNMP/LLDP et normalise les données.
- **Normaliseur / Enrichisseur** : module qui transforme la sortie du scanner en objets Device/Interface/Link.
- **Base de données** : BDD ; schéma simple devices/interfaces/links/events.
- **Topologie engine** : construit le graphe et expose une API pour récupérer le graph sérialisé.
- **Backend API** : JS qui sert l'inventaire, la topologie, endpoints scan/export.
- **Frontend** : application web utilisant une librairie de graph (vis-network, cytoscape.js ou sigma.js) pour l’affichage interactif.

---

# Modèle de données : Schéma minimal

**Device**
- id (UUID)
- hostname
- management_ip
- vendor
- model
- os_version
- serial
- role (switch/router/firewall/host)
- last_seen (timestamp)

**Interface**
- id
- device_id
- name (GigabitEthernet0/1)
- mac
- ip (optional)
- admin_status
- oper_status
- vlan (optional)

**Link**
- id
- src_device_id
- src_interface
- dst_device_id
- dst_interface
- detection_method (LLDP/ARP/manual)
- last_seen

---

# Flux de traitement (pas-à-pas)
1. Lancement du scan (manuel via UI ou via CLI) sur plage/liste d'hôtes.
2. Scanner : ping pour découverte IP vivantes, SNMP GET pour inventory, LLDP pour voisins.
3. Normalisation : convertir réponses SNMP/LLDP en objets Device/Interface.
4. Stockage : insérer/update la base (last_seen mis à jour).
5. Topology engine : reconstruire le graphe à partir des devices/links.
6. Exposition : API fournit le JSON de topologie pour le frontend.
7. Visualisation : frontend consomme l'API et affiche la carte, permet exports.

---

# Exigences techniques & choix d'implémentation

- **Langage** : Python pour backend/scanner (pysnmp, scapy, netmiko, napalm).
- **API** : JavaScript (rapide à développer, simple d'utilisation).
- **Graph engine** : Regarder NetworkX pour la construction + vis-network côté front.
- **Stockage** : MariaDB, PHPMyAdmin, SGBDR
- **Service** : service linux + script (1 fichier pour lancer backend + frontend + db).
- **Authentification** : Basic auth ou token simple pour le PoC (pas de SSO/Gestion AD).
- **Sécurité** : stockage des credentials sur le serveur et chiffré.

---

# KPI et critères de réussite du projet

**Qualitatifs**
- Prototype démontrable et reproductible.
- Interface claire et navigation intuitive lors de la soutenance.
- Documentation complète pour reproduire la démonstration.

**Quantitatifs (objectifs PoC)**
- Taux de découverte sur banc test ≥ 80% (devices détectés et inventoriés).
- Temps pour générer la carte sur banc test : acceptable pour une soutenance (ex. < 5 minutes) — objectif non-contrayant.
- Export fonctionnel (CSV/JSON) pour inventaire et liens.

---

# Ressources & environnement de test nécessaires

## Matériel / virtuel
- 1 machine en guise de serveur sous Linux.
- Un banc test contenant au minimum 3 devices réseau (ex : 2 switches + 1 routeur) et 2 hosts. Alternatives : virutaliser les équipements.

## Accès & comptes
- Accès SNMPv2c community pour les équipements réseaux.
- Accès SSH (si tests d'administration requis) — comptes de test.

## Logiciels
- Python, pip, Node.js, ... (pour frontend build si besoin).

---

# Planning (phases / jalons)

> Remarque : ce planning est une proposition de découpage en phases claires (sprint-like). Adapter selon la durée disponible.

- **Phase 0 — Préparation** : définir un banc test, créer repo.
- **Phase 1 — Scanner & stockage basique** : ICMP + SNMPv2c + LLDP — normalisation et stockage.
- **Phase 2 — Topologie & moteur de graphe** : assembler les liens, tests de cohérence.
- **Phase 3 — Frontend minimal** : afficher topologie, recherche et export.
- **Phase 4 — Scénarios & docs** : écrire le script de soutenance, enregistrer vidéo, finaliser slides et rapport.

---

# Risques, hypothèses et mitigations

- **Risque** : LLDP/LLDP non activé sur les équipements du banc.  
  **Mitigation** : utiliser ARP/Tables MAC ou configurer LLDP.

- **Risque** : accès SNMP refusé ou mal configuré.  
  **Mitigation** : prévoir comptes de secours, utiliser SSH pour extraire certaines infos.

- **Risque** : démonstration live échouant (réseau instable).
  **Mitigation** : préparer une vidéo enregistrée du flux complet ; prévoir jeu de données statique pour le mode démo.

- **Hypothèse** : banc test limité (<= 10 devices).
    PoC dimensionné pour petit périmètre.
    Prévoir une infrastructure assez complexe.

---

# Conclusion

Ce document est la **trame de travail** du projet : il précise ce que nous devons réaliser impérativement, ce que nous pourrons ajouter si le temps le permet, et ce que nous devons éviter pour ne pas perdre la soutenance. L'objectif principal reste simple et mesurable : **récupérer l'information, la stocker et générer une cartographie exploitable**.

---
