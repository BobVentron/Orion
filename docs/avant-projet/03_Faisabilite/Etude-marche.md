# Étude de marché

---

## Contexte du marché

### Taille et dynamique
Le marché mondial des **outils de cartographie réseau** (network mapping / network topology tools) connaît une croissance soutenue.  
Sa taille est estimée entre **$1,2 et $5 milliards**, selon le périmètre considéré (supervision, topologie, automatisation, conformité, etc.).

### Facteurs de croissance
- **Complexité croissante des infrastructures hybrides** (on-premise, cloud, virtualisation, SDN, IoT).
- **Besoin de visibilité en temps réel** : identification rapide des changements, surveillance proactive.
- **Conformité et sécurité** : exigences RGPD, ISO 27001, PCI-DSS, audit et traçabilité.
- **Automatisation et vérification de la configuration** : émergence du “network assurance” et de l’“intent-based networking”.
- **Évolution vers la supervision intégrée** (topologie + monitoring + automatisation).

---

## Public cible

Les principaux utilisateurs de ces outils sont :

| Type d’utilisateur | Objectifs principaux |
|--------------------|----------------------|
| **Grandes entreprises** | Supervision d’infrastructures multi-sites, multi-datacenters, réseaux critiques. |
| **PME** | Réduction des coûts opérationnels, simplification de la gestion réseau. |
| **ESN / infogérant** | Gestion multi-clients, visibilité globale, alertes centralisées. |
| **Administrations et organismes publics** | Sécurité, conformité, souveraineté des données. |

---

## Besoins du marché

| Besoin | Description |
|--------|-------------|
| **Découverte automatique** | Identifier dynamiquement les équipements, liens, topologies, changements. |
| **Visualisation interactive** | Cartes topologiques L2/L3, vues logiques, géographiques ou applicatives. |
| **Recherche active** | Recherche d'équipement par MAC, IP, nom. |
| **Informations enrichies** | Détails des interfaces, OS, trafic, VLAN, configuration, version logicielle. |
| **Supervision et alertes** | Détection d’incidents, dérives, dépassements de seuils. |
| **Administration distante** | Connexion SSH/API, exécution de commandes, sauvegarde des configurations. |
| **Reporting / export** | Génération automatique de documentation (PDF, Visio, audits). |
| **Interopérabilité / API** | Intégration avec CMDB, ITSM, SIEM, outils de supervision ou sécurité. |
| **Sécurité** | Gestion des credentials, chiffrement, audit, permissions granulaires. |
| **Tarification flexible** | Licences modulaires selon taille, usage ou modèle SaaS/on-premise. |

---

## Concurrence et solutions existantes

### Analyse comparative

| Outil | Caractéristiques principales | Avantages | Limites |
|-------|------------------------------|------------|----------|
| **SolarWinds Network Performance Monitor / Topology Mapper** | Découverte automatique L2/L3, visualisation topologique, export Visio/PDF, alertes. | Solution mature, riche en fonctionnalités, forte intégration écosystème SolarWinds. | Coût élevé, mise en place complexe, lourdeur de maintenance. |
| **Auvik** | Découverte automatique, cartographie temps réel, alertes intégrées, gestion de configuration, multi-site. | Interface moderne, déploiement rapide, adapté aux ESN et PME. | Tarification par appareil, dépendance cloud, personnalisation limitée. |
| **ManageEngine OpManager** | Découverte SNMP/CDP/LLDP, mapping dynamique, monitoring intégré. | Bon rapport prix/fonctionnalités, interface claire, intégration large. | Moins performant sur topologies complexes ou très grands réseaux. |
| **Paessler PRTG Network Monitor** | Monitoring par “capteurs”, découverte automatique, visualisation réseau. | Flexible, version gratuite, adapté PME/ETI. | Tarification complexe (par capteur), cartographie visuelle limitée. |
| **IP Fabric** | Découverte complète, modélisation topologique, conformité réseau, snapshots. | Très puissant, API riche, parfait pour audit & troubleshooting. | Coût élevé, complexité d’installation. |
| **NetBrain** | Découverte et automatisation des diagnostics, path analysis. | Fort potentiel pour troubleshooting complexe. | Interface lourde, prix élevé, déploiement long. |
| **Zabbix** *(open source)* | Monitoring SNMP/agent, découverte, alertes, dashboards. | Gratuit, personnalisable, grande communauté. | Interface technique, cartographie peu ergonomique. |
| **LogicMonitor / Datadog (module réseau)** | Découverte API/SNMP, cartographie cloud/on-prem, alertes intelligentes. | Très bon pour environnements hybrides et cloud. | Coût élevé, cartographie secondaire. |
| **Mercator (open source – France)** | Cartographie SI basée sur le modèle ANSSI, documentation, vues applicatives, métiers et flux. | Conforme aux standards ANSSI, open source, adapté aux organisations publiques et européennes. | Peu orienté “découverte automatique réseau”, pas de supervision temps réel. |

---

## Opportunités et positionnement

### Valeur ajoutée potentielle du projet
- **Cartographie réseau simple et précise**, physique et logique.
- **Découverte et mise à jour automatique** des équipements.
- **Visualisation interactive et temps réel**.
- **Intégration d’outils d’administration distante** et d’alertes intégrées.
- **Documentation automatique** et conformité intégrée (audit, snapshots, rapports).

### Différenciateurs possibles

| Axe | Différenciation |
|------|----------------|
| **Précision du lien** | Identification exacte des interfaces, VLAN, sous-réseaux. |
| **Temps réel** | Détection de dérive instantanée, historique des modifications. |
| **UX moderne** | Navigation fluide entre vues logiques, physiques et historiques. |
| **Administration distante** | Commandes SSH/API, sauvegardes, mises à jour. |
| **Sécurité intégrée** | Gestion sécurisée des credentials, chiffrement, audit. |
| **Tarification flexible** | Freemium, licences PME, ou forfaits par usage. |

---

## Spécificités du marché européen

### Tendances régionales
Le marché européen, notamment français, présente des **besoins spécifiques** :
- Forte **sensibilité à la souveraineté des données** (préférence pour l’hébergement en France/UE).
- Priorité à la **conformité réglementaire** (RGPD, ISO 27001, ANSSI, SecNumCloud).
- Demande croissante d’outils **open source ou européens**, perçus comme plus transparents.
- Tissu dense de **PME, collectivités et administrations**, souvent sous-équipées en solutions de cartographie modernes.

### Législation et conformité

| Cadre légal / normatif | Implication pour les outils |
|------------------------|-----------------------------|
| **RGPD (Règlement Général sur la Protection des Données)** | Stockage et traitement de données réseau potentiellement sensibles → respect du consentement, traçabilité, sécurité des accès, hébergement UE. |
| **Directive NIS2 (UE)** | Obligation de cybersécurité renforcée pour les opérateurs essentiels et services numériques. |
| **Référentiels ANSSI / SecNumCloud** | Pertinent pour les solutions destinées aux administrations françaises et secteurs critiques. |
| **Normes ISO 27001 / 27002** | Bonnes pratiques de sécurité, audit, continuité d’activité. |
| **Souveraineté numérique** | Favorise des solutions européennes, open source, ou hébergées localement. |

### Opportunités régionales
- **Marché français et européen encore sous-adressé** par des solutions complètes et locales.
- **Mercator** montre un intérêt croissant pour des outils conformes aux cadres ANSSI, mais sans composante “découverte réseau”.
- Une solution **européenne, automatisée, sécurisée et simple d’usage** a donc un positionnement pertinent.

---

## Risques et barrières à l’entrée
- **Complexité technique** de la découverte multi-vendor (SNMP, CDP, LLDP, OSPF, API propriétaires).
- **Interopérabilité** et scalabilité pour grands réseaux.
- **Sécurité et gestion des accès sensibles**.
- **Concurrence installée** (solutions reconnues, forte notoriété).
- **Modèle économique** à adapter (PME vs grands comptes).

---

## Conclusion et recommandations stratégiques

1. **Lancer un MVP** centré sur :
   - Découverte réseau automatique (L2/L3).
   - Visualisation topologique interactive.
   - Système de recherche simple et documentation automatique.

2. **Cibler d’abord le marché européen**, avec :
   - Conformité RGPD / ANSSI.
   - Hébergement souverain (France ou UE).

3. **Miser sur l’expérience utilisateur (UX)** :
   - Interface fluide, claire, orientée cas d’usage.
   - Navigation entre vues logiques, physiques et métiers.

4. **Modèle économique souple** :
   - Version freemium pour PME / intégrateurs.
   - Modules additionnels (conformité, supervision avancée, reporting).

5. **Positionnement marketing** :
   - “Cartographie réseau intelligente et souveraine”.
   - “Simple, automatisée, sécurisée et conforme aux exigences européennes”.

---

## Synthèse du positionnement

| Marché cible | Proposition de valeur | Différenciateur clé |
|---------------|----------------------|----------------------|
| **PME / ETI / ESN européens** | Cartographie réseau interactive, automatisée et conforme RGPD | Simplicité + souveraineté + automatisation |
| **Administrations / secteur public** | Solution open source / hébergée localement, intégrée avec les standards ANSSI | Souveraineté + conformité |
| **Entreprises multi-sites / hybrides** | Découverte multi-vendor + alertes temps réel + reporting | Visibilité globale + fiabilité + interopérabilité |