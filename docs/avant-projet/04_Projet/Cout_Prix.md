# Analyse des coûts, stratégie de tarification et rentabilité prévisionnelle

**Version** : 1.1
**Date** : 2025-10-11
**Auteurs** : Alexis LONJON
**Objectif** : analyser le coût du projet et préparer une stratégie de tarification efficace et rentable.

---

# Introduction et contexte
Le projet vise à concevoir un **outil de cartographie et de supervision réseau auto-hébergé**, modulaire et extensible.
Ce document a pour objectif de cadrer :
- Les **coûts de développement et de test**,
- Le **positionnement tarifaire** face à la concurrence,
- Les **scénarios de tarification possibles** (freemium, payant, modulaire),
- Et d’évaluer la **rentabilité prévisionnelle** du produit.

---

# Coûts du projet

Cette partie détaille **l’ensemble des coûts associés au développement, aux tests et à la mise en place de l'outil**, incluant la valorisation du travail, le matériel, et les dépenses annexes.

## 1. Ressources humaines
Le coût du travail représente la partie la plus importante du budget du projet.  
Bien que le travail soit réalisé dans le cadre d’un projet universitaire, il est essentiel de **valoriser le temps passé** pour en estimer le coût économique réel.

| Élément | Calcul |
|----------|---------|
| Nombre de personnes | 4 |
| Temps par semaine | 10h |
| Durée du projet | 26 semaines (~6 mois) |
| Total d’heures | 4 × 10h × 26 = **1 040 h** |

### Hypothèses de valorisation horaire
- **Taux horaire d’un étudiant ingénieur** : 25–30 €/h
- **Taux horaire d’un ingénieur confirmé** : 40–50 €/h

| Scénario | Taux horaire | Coût total |
|-----------|--------------|-------------|
| Étudiant (30 €/h) | 30 € × 1 040 h | **31 200 €** |
| Ingénieur confirmé (40 €/h) | 40 € × 1 040 h | **41 600 €** |

> **Coût humain estimé : entre 31 000 € et 42 000 €**

---

## 2. Matériel et infrastructure

Le matériel sert à **tester la solution dans des conditions réelles**, avec un environnement représentatif d’un réseau d’entreprise de petite à moyenne taille.

### Matériel minimum pour PoC
- 1 serveur (8–16 Go RAM, 256–512 Go stockage)
- 4 équipements réseau (3 switchs, 1 routeur)
- 4 postes clients pour test
- Câblage, onduleur, racks basiques

| Élément | Détail | Coût estimé |
|----------|---------|-------------|
| Serveur physique/virtuel | 1 unité | 600 € |
| Switchs/routeurs | 4 équipements | 1 000 € |
| PC/VM clients | 4 machines de test | 1 000 € |
| Câblage / accessoires | — | 300 € |
| **Sous-total** | — | **3 000 €** |

### Matériel pour tests avancés
Pour évaluer l’outil à son plein potentiel :
- 20 équipements réseau (multi-vendor)
- 10 PC clients
- Scénarios complexes (VLAN, redondances, etc.)

| Élément | Détail | Coût estimé |
|----------|---------|-------------|
| Équipements supplémentaires | 16 switches/routeurs | 3 000 € |
| PC clients ou VM supplémentaires | 6 unités | 1 000 € |
| Électricité / hébergement local | 6 mois | 300 € |
| **Sous-total avancé** | — | **4 300 €** |

**Total matériel global : environ 6 000 à 7 000 €**

---

## 3. Coûts annexes

| Élément | Détail | Coût estimé |
|----------|---------|-------------|
| Hébergement divers | Domaine + serveur VPS | 150 € |
| Outils de développement (IDE, GitLab, licences éventuelles) | Logiciels principalement open source | 200 € |
| Communication / support marketing | Affiche, visuels, graphismes | 150 € |
| **Total divers** | — | **500 €** |

---

## 4. Estimation globale

| Catégorie | Estimation basse | Estimation haute |
|------------|------------------|------------------|
| Coût humain | 31 200 € | 41 600 € |
| Matériel | 6 000 € | 7 000 € |
| Divers | 500 € | 500 € |
| **Total global** | **37 700 €** | **49 100 €** |

---

## 5. Conclusion
Le **coût total estimé du projet PoC** se situe entre **38 000 € et 50 000 €**, valorisation incluse.

> Ce coût ne prend pas en compte la valeur réelle des équipements utilisés lors des différents essais. En effet, ces équipements nous sont prêtés par l’IUT et ne génèrent donc aucune dépense directe, bien que leur prix neuf varie généralement entre 1 000 € et 5 000 € par unité.
Pour le projet, nous utiliserons du matériel Cisco, dont le coût est relativement élevé. Le tarif retenu pour la simulation correspond ainsi à celui que l’on pourrait obtenir pour des équipements Cisco reconditionnés ou pour des modèles neufs d’entrée de gamme.

---

# Analyse concurrentielle – Prix et positionnement du marché

| Outil | Type / modèle | Prix moyen | Points forts / limites |
|--------|----------------|-------------|--------------------------|
| **SolarWinds NPM / Topology Mapper** | Payant | 2 500 – 15 000 €/an | Très complet, mais coûteux et lourd. |
| **Auvik** | SaaS | 15 €/équipement/mois | Simple, rapide, mais cloud-only. |
| **ManageEngine OpManager** | Freemium + payant | 500 – 5 000 €/an | Interface riche, modularité correcte. |
| **Paessler PRTG Network Monitor** | Freemium (100 capteurs) | 1 600 €/500 capteurs | Référence du marché, peu flexible sur mesure. |
| **IP Fabric** | Entreprise | > 15 000 €/an | Très complet, orienté gros comptes. |
| **NetBrain** | Entreprise | > 20 000 €/an | Puissant, mais complexe et coûteux. |
| **Zabbix** | Open source | Gratuit | Complexe à configurer, interface datée. |
| **LogicMonitor / Datadog (module réseau)** | SaaS | 20–50 €/équipement/mois | Excellente visibilité, coût élevé. |
| **Mercator (France)** | Open source | Gratuit | Interface légère, peu adaptée aux grandes topologies. |

## Comparaison synthétique

| Catégorie | Exemples | Positionnement |
|:-----------|:----------|:---------------|
| SaaS haut de gamme | LogicMonitor, Datadog, Auvik | Couverture large, coût élevé |
| Solutions industrielles | SolarWinds, NetBrain, IP Fabric, PRTG | Fiables, mais complexes |
| Open-source | Zabbix, Mercator | Faible coût, intégration nécessaire |

## Positionnement

Notre solution se positionne entre :
- **Les outils open-source complexes** (Zabbix, Mercator)
- et **les solutions commerciales coûteuses** (PRTG, ManageEngine).

Elle vise à offrir :
- Une **cartographie réseau automatique et claire**
- Une **auto-hébergement total** (aucune donnée externe)
- Un **modèle économique accessible**
- Une **architecture modulaire** permettant une montée en gamme

Cible principale : **PME / prestataires IT / collectivités / établissements éducatifs.**

---

# Modèle de tarification – Stratégies, analyse comparative et justification

## 1. Objectif général

L’objectif de la stratégie de tarification est de concevoir un modèle économique :

- Abordable et attractif pour les **petites entreprises** (PME, TPE, MSP),
- Suffisamment flexible pour évoluer vers des **clients plus grands**,
- Avec une trajectoire de **monétisation claire et durable**,
- Et garantissant une **adoption rapide** grâce à une faible barrière d’entrée.

Tous les **équipements détectés** dans la cartographie (postes clients, serveurs, équipements réseau, périphériques SNMP, etc.) sont comptabilisés comme **endpoints**.  
Ces endpoints représentent la base du calcul des paliers ou licences, car ils influencent directement la charge de découverte, de supervision et de stockage.

---

## 2. Option A — Modèle Freemium avec modules payants

### 2.1. Principe

Ce modèle repose sur une **version gratuite** du produit, limitée mais fonctionnelle, qui permet à un utilisateur de tester l’outil et de générer de la valeur dès le premier jour.  
Les fonctionnalités plus avancées (supervision, alertes, automatisation, sécurité, reporting, etc.) sont proposées sous forme de **modules payants**.

Cette approche facilite la diffusion initiale du produit et la transformation des utilisateurs gratuits en clients payants une fois les bénéfices démontrés.

### 2.2. Détail de l’offre

#### Version gratuite (Freemium)
- Découverte automatique (SNMP / SSH / LLDP)
- Cartographie réseau basique accessible via interface web
- Stockage et historique limités
- Export CSV
- 1 utilisateur par instance
- Pas de système d’alerte ni d’automatisation
- Idéal pour les PoC et les premières démonstrations

#### Modules payants (Add-ons)

| Module | Prix mensuel | Prix annuel | Description | Justification |
|:--|--:|--:|:--|:--|
| Alerte et gestion d’événements | 99 € | 990 € | Notifications, corrélation et gestion des alertes | Cœur de la valeur opérationnelle — monitoring actif, règles, escalade, intégration email/Slack/Teams |
| RBAC avancé + SSO / Provisioning | 79 € | 790 € | Gestion fine des droits utilisateurs, intégration LDAP/AD, SSO | Exigence sécurité pour comptes multi-équipes / clients entreprises |
| Journalisation centralisée | 129 € | 1 290 € | Collecte et indexation de logs réseau | Stockage + recherche de logs, utile pour troubleshooting et conformité |
| Automatisation / Playbooks / Onboarding | 149 € | 1 490 € | Scripts d’administration automatisée | Automation = fort levier ROI pour clients qui veulent réduire le MTTR |
| Scheduler / tâches planifiées | 49 € | 490 € | Exécution automatique des scans, sauvegardes ou tâches récurrentes | Tâches récurrentes, scans, backups programmés |
| Backup / Firmware update | 129 € | 1 290 € | Sauvegarde de configuration et gestion du firmware | Fonctionnalité critique pour gestion de parc et sécurité |
| Export Visio / Draw.io | 29 € | 290 € | Export de topologie réseau vers formats visuels | Export utile pour documentation & intégration CIO / audits |

> **Remarque :** les prix annuels correspondent à 10× le prix mensuel (incitation à l’annualisation).

### 2.3. Bundles recommandés

| Pack | Contenu | Limite d’équipements | Prix mensuel | Prix annuel |
|:--|:--|:--|--:|--:|
| Pro SMB | Alertes + RBAC + Export + Scheduler | Jusqu’à 250 équipements | 299 € | 2 990 € |
| Business | Pro + Logging + Automatisation | Jusqu’à 1 000 équipements | 899 € | 8 990 € |
| Enterprise | Business + SSO + SLA + intégrations | Plus de 1 000 équipements | Sur devis | Sur devis |

Remarque :
Les endpoints incluent tous les équipements détectés : serveurs, PC, commutateurs, routeurs, points d’accès, etc.
Par exemple, une PME disposant de 150 postes clients, 20 serveurs et 30 équipements réseau totalise environ **200 équipements**, relevant du pack **Pro SMB**.

### 2.4. Tarification complémentaire pour grands comptes
- Possibilité de facturation **par équipement** au-delà d’un certain seuil :
  **0,5 à 1 € / device / mois**, avec tarif dégressif au-delà de 2 000 équipements.
- Alignement sur les modèles pratiqués par **Auvik**, **IP Fabric** ou **LogicMonitor**.

### 2.5. Avantages du modèle Freemium
- **Adoption rapide** : la version gratuite élimine les freins à l’entrée et sert de démonstration concrète.  
- **Effet de réseau** : les utilisateurs gratuits contribuent à diffuser le produit.  
- **Conversion naturelle** : une fois le besoin identifié, la migration vers un module payant devient évidente.  
- **Grande flexibilité commerciale** : possibilité d’adapter la tarification par module, par pack ou par équipement.  
- **Positionnement concurrentiel clair** : accessible comme Zabbix mais avec support et simplicité d’usage supérieurs.

### 2.6. Inconvénients
- **Revenus initiaux faibles** : nécessité d’un volume important d’utilisateurs pour amortir les coûts initiaux.  
- **Support minimal à prévoir** pour la base gratuite afin d’éviter des coûts excessifs de service client.

---

## 3. Option B — Produit payant de base avec modules additionnels

### 3.1. Principe

Dans ce modèle, la version de base est payante, même pour un usage limité.  
Les fonctionnalités supplémentaires sont proposées sous forme de modules additionnels.  
Cela favorise un chiffre d’affaires immédiat, mais ralentit l’adoption initiale.

### 3.2. Exemple de tarification annuelle

| Licence de base | Nombre d’équipements | Prix annuel |
|:--|:--:|--:|
| Base 100 | Jusqu’à 100 | 1 200 € |
| Base 500 | 101 à 500 | 3 000 € |
| Base 500+ | 501 à 1000 | 5 000 € |

Modules additionnels : mêmes prix que ceux proposés dans l’option Freemium.

### 3.3. Avantages
- Génère des **revenus immédiats** dès la première vente.
- Positionne le produit dans une **gamme professionnelle** et renforce la perception de valeur.

### 3.4. Inconvénients
- Freine la **découverte spontanée** du produit.  
- Moins compétitif face aux offres gratuites (Zabbix, NetXMS).  
- Risque de comparaison directe avec des concurrents établis (PRTG, SolarWinds).

---

## 4. Option C — Tarification par palier d’équipements (modèle per-device)

### 4.1. Principe

La tarification est basée sur le nombre total d’équipements supervisés.  
Chaque palier inclut un ensemble de fonctionnalités correspondant à un segment de marché.

### 4.2. Exemple de paliers annuels

| Plan | Nombre d’équipements | Fonctions principales | Prix annuel |
|:--|:--:|:--:|--:|
| Starter | Jusqu’à 25 | Découverte et cartographie basique | Gratuit |
| SMB | Jusqu’à 100 | Alertes simples + export CSV | 500 € |
| Business | Jusqu’à 500 | Alertes avancées + RBAC + 1 module inclus | 2 000 € |
| Enterprise | Plus de 500 | SSO, automatisation, support dédié | Sur devis |

### 4.3. Avantages
- **Lisibilité maximale** : le client comprend facilement le coût selon la taille de son parc.  
- **Facilité d’upsell** : passage simple d’un palier à un autre.  
- **Modèle connu et accepté** sur le marché (aligné sur Auvik, IP Fabric, etc.).

### 4.4. Inconvénients
- Les **sauts de palier** peuvent créer une sensibilité au prix.  
- Le décompte précis des équipements nécessite un suivi technique rigoureux.

---

## 5. Modèle économique final – Freemium, Plugins, Bundles et Paliers combinés

### 5.1. Logique générale du modèle

Le modèle retenu repose sur **trois niveaux de construction tarifaire**, permettant une flexibilité maximale tout en conservant une trajectoire de rentabilité claire :

1. **Vente unitaire (modules à la carte)** :  
   Les clients peuvent activer un ou plusieurs plugins individuellement selon leurs besoins spécifiques.

2. **Bundles fonctionnels (packs de plugins)** :  
   Plusieurs plugins regroupés à tarif préférentiel. Ces bundles ciblent les PME/ETI souhaitant des fonctionnalités cohérentes sans surpayer chaque module séparément.

3. **Grands packs (offres complètes)** :  
   Offres combinant à la fois un **nombre d’équipements maximum inclus** et **plusieurs modules intégrés par défaut**. Ces packs couvrent les besoins globaux (fonctionnalités + volumétrie).

Ce modèle repose sur une logique claire :
> “Tout est disponible à l’unité, mais plus on regroupe, plus le coût unitaire diminue.”

---

### 5.2. Structure tarifaire générale

#### Niveau 1 – Freemium
| Élément inclus | Détails |
|:--|:--|
| Découverte automatique | SNMP, SSH, LLDP |
| Cartographie réseau | Interface web, visualisation dynamique |
| Stockage limité | Données sur 7 jours |
| Export CSV | Oui |
| Utilisateur unique | 1 admin |
| Équipements inclus | Jusqu’à **100 équipements (endpoints)** |
| Prix | Gratuit |

> Objectif : favoriser l’adoption et servir de démonstration produit.  

---

### 5.3. Niveau 2 – Modules payants à la carte (Plugins Add-ons)

Chaque module (plugin) est vendable séparément, activable en un clic depuis l’interface.  
Le client peut composer son environnement selon ses besoins fonctionnels.

| Plugin | Prix mensuel | Prix annuel | Description |
|:--|--:|--:|:--|
| Alerte & Supervision | 39 € | 390 € | Gestion avancée des alertes et supervision |
| RBAC avancé & SSO | 29 € | 290 € | Gestion des accès, intégration AD/SSO |
| Journalisation centralisée | 49 € | 490 € | Collecte et recherche des logs réseau |
| Automatisation / Playbooks | 59 € | 590 € | Exécution de scripts et automatisations |
| Scheduler / Tâches planifiées | 19 € | 190 € | Planification de scans et tâches automatiques |
| Backup / Firmware update | 39 € | 390 € | Sauvegarde et restauration de configurations |
| Export Visio / Draw.io | 9 € | 90 € | Export graphique et reporting visuel |

> Ces plugins peuvent être achetés individuellement ou intégrés dans un bundle.  
> Réduction automatique de **10 à 20 %** selon le nombre de plugins activés simultanément.

---

### 5.4. Niveau 3 – Bundles fonctionnels (packs de plugins)

Les bundles regroupent plusieurs plugins avec un **tarif réduit** pour encourager la montée en gamme.  
Ils **n’incluent pas de limite d’équipements**, celle-ci dépend du palier choisi.

| Bundle | Contenu inclus | Réduction appliquée | Prix mensuel | Prix annuel |
|:--|:--|:--:|--:|--:|
| **Starter** | Alerte & Supervision + Scheduler / Tâches planifiées + Export Visio/Draw.io | 10 % | 59 € | 590 € |
| **Pro** | Starter + RBAC avancé & SSO | 12 % | 82 € | 820 € |
| **Business** | Pro + Journalisation centralisée + Automatisation / Playbooks | 15 % | 142 € | 1 420 € |
| **Enterprise** | Business + Backup / Firmware update + Support Premium | 15 % | 195 € | 1 950 € |
| **Ultimate** | Tous les plugins + options à la carte selon besoins du client | Sur devis | Sur devis | Sur devis |
| **Reporting & Services** | Alerte & Supervision + Journalisation centralisée + Export Visio/Draw.io | 10 % | 85 € | 850 € |
| **Prestataire Pro** | Automatisation / Playbooks + Journalisation centralisée + Backup / Firmware update + Export Visio/Draw.io | 12 % | 130 € | 1 300 € |

> Ces bundles peuvent être associés à un palier d’équipements, permettant au client de choisir la taille de son infrastructure sans payer pour des fonctionnalités inutiles.

---

### 5.5. Niveau 4 – Paliers d’équipements

Chaque licence ou pack inclut un **nombre maximum d’équipements** supervisables.  
Les endpoints comprennent tous les postes clients, serveurs, routeurs, commutateurs, bornes Wi-Fi et autres dispositifs réseau.

| Palier | Équipements max supervisables | Prix mensuel (HT) | Prix annuel (HT) | Commentaire / stratégie |
|---|---|---|---|---|
| Free / Starter | Jusqu’à 100 | **0 €** | **0 €** | Freemium, fonctionnalités limitées |
| Basic / SMB | Jusqu’à 250 | 15 € | 150 € | Pour petites structures |
| Standard / Pro | Jusqu’à 750 | 49 € | 490 € | PME classiques |
| Business | Jusqu’à 2 000 | 139 € | 1 390 € | Réseaux étendus |
| Enterprise | Jusqu’à 5 000 | 299 € | 2 990 € | Grandes entreprises |
| Ultimate / Global | > 5 000 | Sur devis | Sur devis | Tarification personnalisée |

> Le tarif “base” correspond à la gestion de la cartographie, découverte, stockage et monitoring minimal.  
> Les plugins ou bundles viennent s’y **ajouter** selon le besoin du client.

---

### 5.6. Niveau 5 – Packs complets (fonctionnalités + équipements)

Ces **grands packs** combinent à la fois un **nombre d’équipements inclus** et un **ensemble de fonctionnalités** (bundles).  
Ils représentent l’offre “clé en main” la plus complète.

| Pack complet | Contenu fonctionnel | Équipements inclus | Prix mensuel | Prix annuel | Réduction globale |
|:--|:--|:--:|--:|--:|--:|
| **Starter Pack** | Bundle Starter | Jusqu’à 100 équipements | 55 € | 550 € | 5 % |
| **SMB Pack** | Bundle Pro | Jusqu’à 250 équipements | 79 € | 790 € | 5 % |
| **SMB Plus Pack** | Bundle Reporting & Services | Jusqu’à 250 équipements | 75 € | 750 € | 5 % |
| **Business Pack** | Bundle Business | Jusqu’à 750 équipements | 125 € | 1 250 € | 5 % |
| **Business Advanced Pack** | Bundle Prestataire Pro | Jusqu’à 750 équipements | 140 € | 1 400 € | 5 % |
| **Enterprise Pack** | Bundle Enterprise | Jusqu’à 2 000 équipements | 230 € | 2 300 € | 5 % |
| **Corporate Pack** | Bundle Enterprise | Jusqu'à 5 000 équipements | 410 € | 4 100 € | 5 % |
| **Corporate Plus Pack** | Bundle Ultimate + support prioritaire | Plus de 5 000 équipements | Sur devis | Sur devis | Tarification personnalisée |

> Ces packs visent les clients souhaitant une solution globale sans configuration granulaire.

---

### 5.7. Rallonges d’équipements (extensions)

Pour éviter une montée forcée vers un pack supérieur tout en préservant la rentabilité :

- Le client peut acheter des **rallonges d’équipements** (extension temporaire ou permanente).
- Ces rallonges ajoutent un nombre limité d’équipements à un pack existant.
- Elles coûtent **moins cher que de passer au palier supérieur**, mais **plus cher que la moyenne unitaire d’un pack plus grand** (pour ne pas casser le modèle économique).

| Rallonge | Capacité ajoutée | Prix mensuel | Prix annuel | Conditions |
|:--|--:|--:|--:|:--|
| **+25 équipements** | +25 | 8 € | 80 € | Disponible dès le pack SMB |
| **+50 équipements** | +50 | 15 € | 150 € | Limité à deux rallonges par pack |
| **+100 équipements** | +100 | 25 € | 250 € | Réservé aux clients Pro/Business |

**Exemple concret :**
- Un client sur le pack **Basic / SMB (250 équipements)** atteint 280 équipements.
- Il peut acheter une **rallonge +50** à 150 €/an.
- Cela reste **moins cher** que le passage au pack supérieur Standard (490 €/an),
  tout en **restant rentable** pour l’éditeur (coût marginal couvert).

---

### 5.8. Synthèse du fonctionnement commercial

| Composant | Fonction | Prix typique | Cible |
|:--|:--|--:|:--|
| Freemium | Entrée gratuite, découverte et carto | 0 € | TPE, PoC, partenaires |
| Plugins | Fonctionnalités spécifiques | 9–59 €/mois | PME, ETI |
| Bundles | Groupe de plugins cohérents | 59–195 €/mois | PME, ETI |
| Paliers d’équipements | Capacité maximale d’inventaire | 15–299 €/mois | Tous segments |
| Packs complets | Bundle + palier inclus | 55–410 €/mois | PME, ETI, grandes entreprises |
| Rallonges | Extension de capacité ponctuelle | 9–25 €/mois | Clients existants |


---

### 5.9. Stratégie commerciale associée

1. **Adoption par le Freemium**
   - Objectif : générer du volume et démontrer la valeur.
   - Cible : TPE, intégrateurs, MSP.
   - Conversion estimée : 10–15 % vers offres payantes.

2. **Montée en valeur via plugins / bundles**
   - Objectif : proposer une modularité maximale.
   - Le client paie uniquement ce dont il a besoin, favorisant la satisfaction et la conversion.

3. **Segmentation claire par taille d’infrastructure**
   - Les paliers d’équipements structurent la gamme selon la taille du parc supervisé.

4. **Packs complets pour les clients matures**
   - Ciblent les PME/ETI souhaitant centraliser tous les modules sans gestion complexe.
   - Positionnement “clé en main” avec remises attractives.

5. **Rallonges pour la flexibilité**
   - Outil de fidélisation évitant les ruptures d’abonnement.
   - Maintient la marge tout en offrant une option économique au client.

---

### 5.10. Conclusion

Le modèle final combine la **flexibilité du Freemium**, la **modularité des plugins**, et la **progressivité des paliers** :

- **Entrée gratuite** pour adoption rapide,  
- **Upsell progressif** par modules ou bundles,  
- **Paliers lisibles** selon le nombre d’équipements,  
- **Rallonges limitées** pour flexibilité sans cannibalisation,  
- **Réductions par volume** pour encourager les packs globaux.

Ce système de tarification permet de **vendre à tous les niveaux** :
- de la petite structure curieuse,
- à la PME en phase d’expansion,
- jusqu’à l’ETI ou au grand compte cherchant une solution complète.

L’ensemble constitue un modèle équilibré, évolutif et durable, conciliant **accessibilité commerciale** et **rentabilité à moyen terme**.

---

## 6. Scénarios de rentabilité (projection sur 3 ans)

### Hypothèses de base

- Lancement avec une version **Freemium** servant d’acquisition de masse.
- Taux de conversion estimé de **10 à 15 %** vers des offres payantes sur 3 ans.
- Coût marginal faible par client (support, maintenance).
- Croissance organique et marketing progressive.
- **Investissement initial de conception : 37 700 à 49 100 €** (coûts humains, matériel et divers).

---

### Projection globale

| Scénario | Clients payants (année 1) | ARPC (revenu annuel moyen par client) | Croissance annuelle du parc client | Revenus année 1 | Revenus année 2 | Revenus année 3 |
|:--|--:|--:|--:|--:|--:|--:|
| **Conservateur** | 30 | 800 € | +50 % | **24 000 €** | **36 000 €** | **54 000 €** |
| **Modéré** | 80 | 1 100 € | +70 % | **88 000 €** | **149 600 €** | **254 320 €** |
| **Agressif** | 250 | 1 500 € | +100 % | **375 000 €** | **750 000 €** | **1 500 000 €** |

---

### Décomposition du revenu moyen (ARPC)

| Composant | Description | Contribution moyenne |
|:--|:--|--:|
| **Base (palier équipements)** | De 250 à 2 000 équipements selon taille client | 300 € à 1 500 € |
| **Plugins / Bundles** | 2 à 5 modules ou un bundle complet | +500 € à +1 200 € |
| **Rallonges / extensions** | Clients en croissance ajoutant du volume | +100 € à +300 € |
| **ARPC total** | Moyenne pondérée des abonnements annuels | **800 € à 1 500 €** |

---

### Lecture et interprétation

- Le scénario **modéré** permet d’atteindre le **seuil de rentabilité** dès la **fin de la 2ᵉ année**, avec environ **150 000 € de revenus récurrents**.  
- Le scénario **agressif**, basé sur une forte traction freemium et un marketing efficace, dépasse **1,5 M € de revenus annuels** à 3 ans, positionnant la solution comme un **SaaS B2B rentable et scalable**.  
- Le scénario **conservateur** reste soutenable : la croissance progressive assure une **amortisation du coût initial (≈40 000 €)** d’ici la **3ᵉ année**.

> 🔹 **Freemium = moteur d’acquisition**  
> 🔹 **Bundles = moteur d’upsell**  
> 🔹 **Packs = moteur de fidélisation**

---

### Visualisation de la croissance projetée

| Année | Scénario conservateur | Scénario modéré | Scénario agressif |
|:--|--:|--:|--:|
| **Année 1** | 24 000 € | 88 000 € | 375 000 € |
| **Année 2** | 36 000 € | 149 600 € | 750 000 € |
| **Année 3** | 54 000 € | 254 320 € | 1 500 000 € |
| **Croissance cumulée (3 ans)** | +125 % | +189 % | +300 % |

---

### Intégration du coût de conception initial

| Élément | Estimation | Commentaire |
|:--|--:|:--|
| **Investissement initial (conception)** | 37 700 – 49 100 € | Développement, matériel, mise en place initiale |
| **Charges fixes annuelles** | ~50 000 € | Support, marketing, développement |
| **Marge brute** | 80–85 % | Typique d’un modèle SaaS B2B |
| **Seuil de rentabilité global (incl. conception)** | ~90 000 € | Atteint courant **année 2 (scénario modéré)** |
| **Potentiel de marge nette à 3 ans** | 35–50 % | Après amortissement complet des coûts initiaux |

---

### Synthèse visuelle

| Année | Revenus cumulés (modéré) | Coûts cumulés estimés | Résultat net estimé |
|:--|--:|--:|--:|
| **Année 1** | 88 000 € | 87 700 € *(investissement + charges)* | **≈ 300 €** |
| **Année 2** | 237 600 € | 137 700 € | **≈ +99 900 €** |
| **Année 3** | 491 920 € | 187 700 € | **≈ +304 200 €** |

> **Retour sur investissement (ROI)** : entre **+200 % et +300 % à 3 ans** selon le scénario retenu.

---

## 7. Synthèse finale

| Élément | Recommandation |
|:--|:--|
| **Modèle principal** | Freemium + Plugins Add-ons + Bundles + Paliers d’équipements |
| **Structure tarifaire** | Entrée gratuite, modules à 29–149 €/mois, bundles à partir de 159 €/mois |
| **Paliers d’équipements** | 100 (gratuit), 250, 750, 2 000, 5 000+ |
| **Cibles prioritaires** | TPE, PME, intégrateurs, MSP, ETI |
| **Bundles phares** | Pro (RBAC, supervision, planification), Business (automatisation + logs), Enterprise (tout inclus) |
| **Facturation alternative** | Option par équipement : **0,5 à 1 €/device/mois** |
| **Stratégie de montée en gamme** | Freemium → Plugins → Bundle → Pack complet |
| **Avantages compétitifs** | Simplicité, modularité, support premium, souveraineté des données |
| **Positionnement marché** | Entre **Zabbix (gratuit et complexe)** et **Auvik (premium et cher)** |
| **Objectif principal** | Maximiser l’adoption initiale et augmenter la conversion vers les offres payantes |
| **Vision à 3 ans** | Atteindre entre **250 et 1 000 clients payants**, avec un ARR entre **250 000 € et 1,5 M €** |
| **Moteurs de croissance clés** | ① Acquisition Freemium ② Upsell via Bundles ③ Fidélisation via Packs ④ Support & communauté |

---

## 8. Conclusion

Le modèle **Freemium modulaire avec tarification par paliers** est le plus adapté à une stratégie de croissance durable.
Il permet de :

- Favoriser une **adoption rapide** sur le marché, notamment pour les démonstrations,
- Garantir une **progression naturelle vers des offres payantes**,
- Maintenir une **structure tarifaire lisible** basée sur le nombre réel d’équipements,
- Et préparer une **scalabilité économique** à mesure que la base client s’élargit.