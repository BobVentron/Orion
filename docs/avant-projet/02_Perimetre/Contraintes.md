# Contraintes, livrables et limites du projet

## Table des matières
1. [Ce qui est dans le projet (In-Scope)](#ce-qui-est-dans-le-projet-in-scope)
2. [Ce qui est hors du projet (Out-of-Scope)](#ce-qui-est-hors-du-projet-out-of-scope)
3. [Avant-projet : livrables et tâches](#avant-projet--livrables-et-tâches)
4. [Contraintes](#contraintes)
5. [Risques majeurs et mitigation](#risques-majeurs-et-mitigation)

---

# Ce qui est dans le projet (In-Scope)
- Découverte automatique des équipements (SNMP/SSH/ICMP/LLDP)
- Stockage et traitement des information
- Visualisation de la topologique interactive
- Export CSV/JSON/PNG

---

# Ce qui est hors du projet (Out-of-Scope)
- Gestion utilisateurs / RBAC
- Prise en main à distance
- Documentation et recommandations d'architecture
- Alerting basique
- Inventaire centralisé (DB + graphe)
- Sauvegarde/restauration configurations
- Monitoring avancé (NetFlow/sFlow)
- ITSM complet
- IPS/IDS avancé
- Remplacement d’un NMS existant
- Multi-tenant complet
- Machine learning pour prédiction incidents

---

# Avant-projet : livrables universitaires
**Livrables attendus**

### Jalon 1 – Fiche Projet
**Objectif :** Définir les contours, objectifs et organisation du projet.
**Livrable :** Document de synthèse (2 pages max) + planning prévisionnel avec répartition des tâches.
**Échéance :** 13 novembre

---

### Jalon 2 – Pitch Public
**Objectif :** Présenter le projet de manière claire et convaincante devant un public d’étudiants et d’enseignants.
**Livrable :** Présentation orale avec support vidéo projeté.
**Échéance :** 11 décembre

---

### Jalon 3 – Élément de Communication
**Objectif :** Créer une affiche papier pour promouvoir le projet de façon synthétique auprès de différents publics (étudiants, professionnels, enseignants).
**Livrable :** Affiche papier de communication.
**Échéance :** 15 janvier

---

### Jalon 4 – Dossier Technique
**Objectif :** Expliquer les choix techniques et le fonctionnement global de la solution.
**Livrable :** Schémas d’architecture, diagrammes UML, documentation technique.
**Échéance :** À déterminer

---

### Jalon 5 – Évaluation du Processus Projet
**Objectif :** Présenter l’organisation interne et la gestion du projet mise en œuvre.
**Livrable :** Répartition effective des tâches, comptes rendus de réunions, notes techniques, décisions et ajustements du planning.
**Échéance :** 27 mars

---

### Jalon 6 – Analyse de Risque
**Objectif :** Réaliser une analyse de risques en lien avec la ressource R5.cyber.12 (cybersécurité).
**Livrable :** Rapport d’analyse de risques.
**Échéance :** À déterminer

---

### Jalon 7 – Rapport d’Opportunité (Mémoire)
**Objectif :** Rédiger un document complet reprenant l’ensemble du projet et son évolution.
**Livrable :** Rapport d’opportunité (mémoire final).
**Échéance :** 26 mai

---

### Jalon 8 – Jury Final : Présentation Client
**Objectif :** Présenter le projet à un potentiel client ou investisseur.
**Livrable :** Présentation orale orientée client + vidéo de démonstration du fonctionnement global.
**Échéance :** 3 juin

---

### Jalon 9 – Jury Final : POC Démonstration
**Objectif :** Réaliser une démonstration technique complète du projet.
**Livrable :** Démonstration technique (POC) + support visuel (type PowerPoint).
**Échéance :** 3 juin

---

# Contraintes

## Techniques
- Protocoles : SNMP, SSH, HTTP(S), LLDP/CDP, ICMP.
- Accès aux équipements : comptes SNMP/SSH/API.
- Non-intrusif : scans planifiés, throttling.
- Base de données et traitement des données.
- API documentée.
- Sécurité : TLS, hash, audit.
- Sauvegarde/reprise planifiée.

---

## Contraintes humaines / organisationnelles

Le projet est réalisé en **équipe de quatre personnes**, ce qui implique une bonne coordination et une communication fluide.
Les principaux points d’attention seront :

- **Organisation interne :** définir clairement les rôles et responsabilités de chacun pour éviter les doublons et les oublis.
- **Communication :** maintenir un échange régulier via des réunions et des outils collaboratifs pour suivre l’avancement.
- **Réactivité :** en cas de problème, prévenir rapidement le groupe afin de trouver une solution collective.
- **Gestion du groupe :** veiller à l’équilibre de la charge de travail et à la motivation de chacun tout au long du projet.
- **Cohésion :** encourager un climat de confiance et de collaboration pour garantir la réussite commune.

---

## Contraintes temporelles

Le calendrier du projet est structuré autour de plusieurs **jalons universitaires** avec des rendus et des soutenances à dates fixes.
Les contraintes principales sont :

- **Multiples livrables à rendre** (fiche projet, pitch, dossier technique, rapport final, etc.) qui exigent une planification détaillée.
- **Charge de travail supplémentaire** liée aux autres cours et aux obligations d’alternance.
- **Risque de retard** si la coordination entre membres n’est pas optimale.
- **Nécessité d’un suivi régulier** du planning et d’ajustements en cas d’imprévus.

Une gestion du temps rigoureuse et une anticipation des périodes de forte charge seront indispensables pour respecter les échéances.

---

## Contraintes budgétaires

Le projet devra également tenir compte de **contraintes économiques** liées à la viabilité du produit sur le marché.
Les points clés à surveiller sont :

- **Positionnement tarifaire :** trouver un prix **attractif mais rentable**, adapté au marché et à la concurrence.
- **Analyse du marché :** identifier les outils ou services similaires existants afin d’ajuster notre offre.
- **Rentabilité :** éviter de se sous-vendre tout en restant compétitifs face aux autres solutions.
- **Équilibre coûts / valeur :** garantir que le prix final reflète la qualité et les fonctionnalités proposées.