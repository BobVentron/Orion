# 🌟 Orion — Outil de Cartographie Réseau

> **Projet PTUT — Duck Inc.**  
> Bastien Soleilhac · Alexis Lonjon · Michel Bermond · Jade Degaugue 
> IUT — Réseaux & Télécommunications | 2025–2026

---

## Présentation

**Orion** est une plateforme de cartographie et de supervision réseau **auto-hébergée**, développée dans le cadre du projet tutoré (PTUT) en 3ème année de BUT Réseaux & Télécommunications.

Le nom fait référence à la constellation d'Orion — symbole de repérage et de navigation — un parallèle direct avec l'objectif de l'outil : **vous guider à travers votre infrastructure réseau**.

### Le constat

Dans le monde de l'IT, la documentation réseau est vitale mais rarement à jour. Lors d'interventions chez des clients, il est courant de trouver des dizaines d'équipements sans aucun schéma topologique disponible, ce qui transforme une intervention de 15 minutes en plusieurs heures de diagnostic.

Orion répond à ce problème : **une seule installation, une cartographie complète en moins de 30 minutes**, maintenue automatiquement à jour.

---

## Fonctionnalités

- **Découverte automatique** du réseau via SNMP v2c/v3, ARP, LLDP/CDP
- **Carte topologique interactive** avec zoom, filtres et recherche
- **Inventaire détaillé** : modèle, firmware, interfaces, IP, VLANs, tables MAC
- **Supervision temps réel** : détection de pannes, interfaces down, métriques
- **Collecte continue** via un daemon Python dédié
- **API REST** exposant l'inventaire et la topologie
- **Interface web** full-stack servie via Nginx
- **Déploiement en un seul paquet Debian** (`.deb`) — Docker requis uniquement

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    Docker Stack                       │
│                                                       │
│  ┌──────────┐   ┌──────────┐   ┌──────────────────┐ │
│  │   WEB    │   │   API    │   │      CLT         │ │
│  │  (Nginx) │◄──│ (Node.js)│◄──│ (Python Scanner) │ │
│  │  :80/443 │   │  :3000   │   │  collector daemon│ │
│  └──────────┘   └────┬─────┘   └──────────────────┘ │
│                       │                               │
│                  ┌────▼─────┐                         │
│                  │    DB    │                         │
│                  │(Postgres)│                         │
│                  └──────────┘                         │
└──────────────────────────────────────────────────────┘
```

| Composant | Technologie | Rôle |
|-----------|-------------|------|
| `API` | Node.js / Express | REST API — interface entre la BDD et le frontend |
| `CLT` | Python / pysnmp | Scanner SNMP, daemon de collecte continu |
| `WEB` | HTML/CSS/JS + Nginx | Interface web + reverse proxy SSL |
| `DB` | PostgreSQL 16 | Stockage de l'inventaire et de la topologie |

---

## Installation rapide

### Prérequis

- Debian/Ubuntu (amd64)
- Docker et Docker Compose installés
- Accès SNMP aux équipements réseau

### Via le paquet Debian (recommandé)

```bash
# Télécharger et installer le paquet
dpkg -i orion_0.5.3_all.deb

# Lancer la configuration initiale
sudo orion-control setup

# Démarrer Orion
sudo orion-control start
```

Le script `orion-control` gère l'ensemble du cycle de vie :

```
orion-control start     # Démarrer la stack Docker
orion-control stop      # Arrêter
orion-control restart   # Redémarrer
orion-control status    # Voir l'état des containers
orion-control logs      # Consulter les logs
orion-control ssl       # Configurer HTTPS (certificat personnalisé ou auto-signé)
orion-control update    # Mettre à jour
```

### Via Docker Compose (développement)

```bash
cd src/
cp .env.example .env   # Configurer POSTGRES_PASSWORD, etc.
docker compose up -d
```

L'interface est accessible sur `http://localhost` (ou `https://` si SSL configuré).

---

## Structure du dépôt

```
orion/
├── src/                        # Code source
│   ├── docker-compose.yml      # Stack Docker complète
│   ├── API/                    # Backend Node.js/Express
│   │   ├── server.js           # Point d'entrée — routes REST
│   │   └── src/db/postgres.js  # Connexion PostgreSQL
│   ├── CLT/                    # Scanner Python (orion_scanner)
│   │   └── app/orion_scanner/
│   │       ├── collector_daemon.py   # Daemon de collecte continu
│   │       ├── cli.py               # Interface CLI
│   │       ├── snmp/                # Modules SNMP (ARP, STP, trunks, topology...)
│   │       └── db/                  # ORM et schéma de la BDD
│   ├── WEB/                    # Frontend + Nginx
│   │   ├── nginx.conf          # Config Nginx (HTTP→HTTPS, reverse proxy)
│   │   └── site/               # Pages HTML/CSS/JS (carto, config, list...)
│   └── DB/                     # Scripts SQL d'initialisation
│       ├── 01-init-orion.sql   # Schéma de la base
│       └── 02-data-orion.sql   # Données initiales (OIDs, constructeurs...)
│
├── debian/                     # Packaging Debian
│   ├── control                 # Métadonnées du paquet
│   ├── preinst                 # Script pré-installation
│   └── postinst                # Script post-installation (setup Docker)
│
├── scripts/
│   ├── orion-control           # Script de contrôle principal (CLI admin)
│   └── dump-local.sh           # Dump de la base de données
│
├── site-vitrine/               # Site marketing Duck Inc. (HTML/CSS/JS statique)
│
└── docs/                       # Documentation du projet
    ├── avant-projet/           # Docs préparatoires (cadrage, périmètre, faisabilité)
    ├── pitch/                  # Texte et présentation du pitch
    ├── gantt/                  # Planification Gantt (GanttProject)
    └── git/                    # Guides Git pour l'équipe
```

---

## Modules de scan SNMP

Le scanner Python (`src/CLT/app/orion_scanner/snmp/`) implémente la découverte via plusieurs protocoles et MIBs :

| Module | Description |
|--------|-------------|
| `client.py` | Client SNMP bas niveau (v2c/v3) |
| `topology.py` | Découverte LLDP/CDP — liens entre équipements |
| `interfaces.py` | État et config des interfaces |
| `vlans.py` | Tables VLAN |
| `check_arp.py` | Table ARP |
| `check_mac_table.py` | Table MAC (CAM) |
| `check_stp.py` | Spanning Tree Protocol |
| `check_trunks.py` | Trunks 802.1Q |
| `check_etherchannel.py` | Agrégats (LACP/PAgP) |
| `check_hsrp.py` | Haute disponibilité HSRP |
| `check_routing.py` | Tables de routage |
| `check_metrics.py` | Métriques (CPU, mémoire, bande passante) |
| `entity.py` | Inventaire matériel (chassis, modules) |

---

## Équipe — Duck Inc.

| Membre | Rôle principal |
|--------|---------------|
| Bastien Soleilhac | Architecture, API, packaging Debian, déploiement |
| Alexis Lonjon | Frontend, CLT/scanner, intégration |
| Michel Bermond | Frontend, intégration, documentation |
| Jade Degaugue | Documentation, présentation, pitch |

---

## Licence

Projet académique — PTUT BUT3 R&T.  
© 2025–2026 Duck Inc. Tous droits réservés.
