# Architecture et conformité — Outil de cartographie réseau auto-hébergé

**Version** : 1.0
**Date** : 2025-10-06
**Auteurs** : Alexis LONJON
**Objectif** : cadrer les aspects d’architecture, de modularité, de conformité légale et de gestion des licences liés à la commercialisation d'un outil de **cartographie réseau auto-hébergé**.

---

# Table des matières

1. [Objectif général](#objectif-général)
2. [Principe d’auto-hébergement](#principe-dauto-hébergement)
3. [Architecture modulaire proposée](#architecture-modulaire-proposée)
4. [Sécurité et gestion des accès](#sécurité-et-gestion-des-accès)
5. [Stockage et gestion des mots de passe](#stockage-et-gestion-des-mots-de-passe)
6. [Conformité légale et réglementaire (France / Europe)](#conformité-légale-et-réglementaire-france--europe)
7. [Système de licences et extensions payantes](#système-de-licences-et-extensions-payantes)
8. [Déploiement et installation](#déploiement-et-installation)
9. [Scénarios d’utilisation typiques](#scénarios-dutilisation-typiques)
10. [Recommandations pour la suite du projet](#recommandations-pour-la-suite-du-projet)

---

# Objectif général

Le but est de concevoir un **outil auto-hébergé** de cartographie, supervision et gestion de réseaux, pouvant être déployé **chez chaque client** de manière isolée et sécurisée. Cet outil devra :

* fonctionner sans dépendre d’un cloud tiers ;
* être modulaire (modules installables séparément selon les besoins) ;
* intégrer une **gestion des licences et extensions payantes** pour une commercialisation progressive ;
* être conforme aux législations européennes (RGPD, cybersécurité, confidentialité) ;
* proposer un contrôle d’accès robuste et traçable.

---

# Principe d’auto-hébergement

L’outil doit pouvoir être installé **sur l’infrastructure du client** (serveur physique ou VM). Aucun transfert de données vers un serveur externe ne doit être nécessaire pour son fonctionnement de base.

Caractéristiques principales :

* Chaque client héberge sa propre instance complète de la solution.
* Les communications entre modules internes restent sur le réseau local.
* Les mises à jour peuvent être distribuées sous forme de paquets ou conteneurs (type .deb / .rpm ou images Docker signées).
* Aucun transfert de logs, inventaires ou configurations ne doit sortir de l’environnement du client sans accord explicite.

---

# Architecture modulaire proposée

L’outil sera structuré en **quatre grands modules indépendants**, interconnectés par API internes. Chaque module pourra être installé sur un même serveur ou réparti sur plusieurs.

## 1. Module de **Collecte / Découverte**

* Scans ICMP, SNMP, LLDP, SSH, API, etc.
* Transforme les données brutes en inventaire structuré.
* Peut être déployé sur plusieurs nœuds pour scanner des sous-réseaux distincts.

## 2. Module de **Stockage / Traitement**

* Base de données centralisée (PostgreSQL, SQLite, ou équivalent sécurisé).
* API interne pour normaliser et exposer les informations aux autres modules.
* Gestion de l’historique et des journaux.

## 3. Module d’**Affichage / Interface web**

* UI interactive : topologie, inventaire, supervision.
* Communication interne via API REST sécurisée (HTTPS, authentification par token).

## 4. Module d’**Administration à distance / Actions**

* Connexion aux équipements via SSH/API pour exécuter des commandes simples.
* Gestion des templates de configuration.
* Enregistrement des actions et traçabilité complète.

Chaque module doit pouvoir être :

* installé indépendamment (paquet dédié ou conteneur) ;
* mis à jour sans dépendance critique ;
* arrêté/redémarré sans impacter les autres composants (microservices loosely coupled).

---

# Sécurité et gestion des accès

L’outil gère plusieurs **rôles utilisateurs** et une politique d’accès fondée sur le principe du **moindre privilège**.

## Rôles principaux

* **Administrateur global** : gère utilisateurs, rôles, modules, configuration du système.
* **Technicien réseau** : accès à la cartographie, inventaire, supervision, exécution d’actions approuvées.
* **Observateur** : lecture seule (topologie, état du réseau, rapports).
* **Auditeur / Sécurité** : lecture + accès aux journaux et historiques d’actions.

Chaque compte utilisateur :

* est **unique** (pas de comptes partagés) ;
* s’authentifie via **mot de passe fort** ou **SSO interne** (LDAP, AD, ou OIDC selon l’environnement) ;
* bénéficie d’une **expiration automatique** de session et d’un **chiffrement TLS** des communications.

Traçabilité : toutes les actions critiques doivent être journalisées avec : horodatage, utilisateur, action, cible, statut.

---

# Stockage et gestion des mots de passe

La gestion des secrets (mots de passe, clés, tokens) doit respecter les meilleures pratiques de sécurité applicative.

## Principes à respecter

1. **Chiffrement au repos** : tous les mots de passe stockés (accès SNMP, SSH, API) doivent être chiffrés dans la base avec un algorithme robuste (AES-256-GCM ou équivalent).
2. **Hash sécurisé pour les comptes utilisateurs** : mot de passe non réversible, stocké avec un algorithme type bcrypt / Argon2.
3. **Séparation des secrets** : utilisation d’un fichier ou coffre-fort chiffré (Vault, Keyring Linux, ou gestionnaire local sécurisé).
4. **Rotation / révocation des accès** : possibilité d’effacer ou remplacer les credentials sans redéploiement complet.
5. **Jamais de mot de passe en clair dans les logs, exports, ou API.**

## Concrètement

* Intégration possible avec **HashiCorp Vault** ou équivalent open-source (passbolt, Bitwarden self-hosted) pour la gestion des clés.
* Pour les environnements simples : stockage chiffré local avec clé unique serveur protégée dans un fichier restreint (`0600`).
* Pour le PoC, un chiffrement symétrique local (Python cryptography / Fernet) suffira pour démontrer la conformité du concept.

---

# Conformité légale et réglementaire (France / Europe)

## 1. **RGPD (Règlement Général sur la Protection des Données)**

L’outil manipule des données techniques (adresses IP, noms d’hôtes, comptes utilisateurs). Ces données sont considérées comme **potentiellement personnelles** lorsqu’elles permettent d’identifier un individu (ex : identifiant d’utilisateur, poste de travail).

### Obligations principales

* **Minimisation des données** : ne collecter que les informations nécessaires à la cartographie.
* **Transparence** : informer les utilisateurs internes du périmètre et des finalités de la collecte.
* **Droits d’accès et de suppression** : prévoir une fonction d’export et de suppression des données liées à un utilisateur.
* **Conservation limitée** : logs et historiques ne doivent pas être conservés indéfiniment.

## 2. **Cybersécurité et conformité technique**

Référence aux cadres normatifs :

* **ANSSI — Référentiel SecNumCloud (principes applicables)** : isolation, intégrité, traçabilité, durcissement système.
* **Directive NIS2** : exigences de sécurité renforcées pour les opérateurs de services essentiels (OSE) — pertinence pour les grands clients.
* **ISO 27001 / 27002** : bonnes pratiques de gestion de la sécurité de l’information (à viser à moyen terme).

### Actions concrètes de conformité

* Utilisation du chiffrement TLS 1.3.
* Signature des paquets ou images Docker distribuées.
* Audit interne avant chaque version stable.
* Possibilité d’intégrer un module de journalisation certifiable (audit log immuable).

---

# Système de licences et extensions payantes

## Objectif

Prévoir un **mécanisme de gestion de licences** permettant de proposer :

* une **version de base gratuite** avec les fonctionnalités essentielles (cartographie, inventaire, affichage minimal) ;
* des **extensions payantes** (modules ou plugins) activables selon le type de licence acquise ;
* un **contrôle automatique** des droits d’utilisation au sein de chaque instance auto-hébergée.

## Principes généraux

1. **Système modulaire de licences** : chaque module ou fonctionnalité avancée (supervision, alerting, administration distante, export avancé) pourra être activé via une clé de licence.
2. **Pas de dépendance cloud obligatoire** : validation locale ou semi-hors ligne des licences pour respecter le principe d’auto-hébergement.
3. **Gestion centralisée dans le module d’administration** :

   * stockage sécurisé des licences (fichier chiffré ou clé signée) ;
   * possibilité d’ajouter, retirer ou renouveler des licences ;
   * affichage de l’état des modules actifs/inactifs.
4. **Audit et conformité** : journalisation des installations ou activations d’extensions pour suivi interne.

## Scénarios possibles de gestion des licences

* **Mode 1 (local complet)** : clé de licence fournie par fichier signé (certificat public/privé) vérifié localement.
* **Mode 2 (vérification ponctuelle)** : communication REST sécurisée vers un serveur de validation (si le client l’autorise).
* **Mode 3 (licence d’entreprise)** : gestion manuelle via contrat avec clé globale pour plusieurs instances.

## Sécurité des licences

* Les licences doivent être **signées numériquement** pour éviter la falsification.
* Le mécanisme doit pouvoir détecter les duplications ou utilisations non autorisées.
* Les licences et modules payants doivent être liés à un **identifiant unique d’instance** (UUID généré à l’installation).

## Intégration technique prévue

* Gestion des extensions via un **système de plugins** : chaque plugin contient un manifeste déclarant son nom, version, dépendances, et type de licence requis.
* Interface utilisateur dédiée pour visualiser les **modules actifs, disponibles ou restreints**.
* API REST pour interroger et activer les extensions sous licence.

---

# Déploiement et installation

## Système cible : Linux (Debian/Ubuntu/CentOS)

Chaque module doit être packagé sous forme :

* de **paquets indépendants (.deb/.rpm)** ou
* de **conteneurs Docker** orchestrés via docker-compose ou Podman.

### Structure recommandée

| Module         | Nom paquet / service  | Dépendances       | Description                                         |
| -------------- | --------------------- | ----------------- | --------------------------------------------------- |
| Collecte       | `networkmapper-agent` | SNMP libs, Python | Exécute les scans et envoie les données au stockage |
| Stockage       | `networkmapper-core`  | PostgreSQL, API   | Centralise et expose les données                    |
| Affichage      | `networkmapper-ui`    | Node.js, React    | Interface utilisateur web                           |
| Administration | `networkmapper-admin` | SSH libs, API     | Gestion distante et supervision                     |

Prend en compte que les pluggins pourront avoir des dépendances supplémentaires.

### Installation typique

1. Installer les paquets nécessaires (`apt install networkmapper-core networkmapper-ui`).
2. Configurer les paramètres d’accès (fichier `/etc/networkmapper/config.yml`).
3. Lancer les services (systemd ou docker-compose).
4. Créer les comptes initiaux (admin, opérateurs, auditeurs).
5. Ajouter les **licences** correspondant aux modules souhaités (base gratuite + extensions payantes).

---

# Scénarios d’utilisation typiques

1. **Entreprise multi-sites** : déploiement d’un module de collecte sur chaque site, centralisation dans un serveur principal d’analyse.
2. **Prestataire / intégrateur** : hébergement d’instances distinctes pour chaque client (mutualisation limitée, isolation stricte).
3. **Grand compte / administration** : architecture distribuée avec haute disponibilité, intégration LDAP/AD, conformité ANSSI.
4. **Utilisation évolutive** : démarrage avec la version gratuite, puis ajout d’extensions payantes (alerting, audit, supervision avancée) selon les besoins.

---

# Recommandations pour la suite du projet

1. **Définir un modèle de déploiement modulaire clair** (type Wazuh, Graylog, ou Zabbix) dès les premières maquettes.
2. **Formaliser la gestion des secrets** (Vault ou équivalent) avant toute intégration de fonctionnalités d’administration distante.
3. **Concevoir un prototype simple de gestion de licences locales** pour démontrer la faisabilité du modèle économique.
4. **Documenter la conformité RGPD** dans la documentation utilisateur (charte interne, mentions légales, politique de conservation).
5. **Prévoir un audit interne** de sécurité avant toute diffusion à des tiers.
6. **Anticiper la certification ou labellisation ANSSI / ISO 27001** si le projet vise le marché public ou les OIV.

---

# Conclusion

Ce document sert de base pour cadrer l’**architecture globale**, la **modularité technique**, la **gestion des licences et extensions payantes** et la **conformité réglementaire** du futur outil.

L’approche auto-hébergée, combinée à un modèle économique flexible (gratuit + modules premium), permet d’assurer à la fois la **maîtrise des données** et la **pérennité du projet**. La prochaine étape consistera à **modéliser le système de licences**, puis à rédiger un **plan technique d’intégration** pour sa mise en œuvre dans le PoC.