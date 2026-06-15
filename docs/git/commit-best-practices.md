# Bonnes pratiques Git — Gestion des commits (Complet)

## Objectif du document
Ce document fournit un guide complet et pratique pour rédiger des commits clairs, cohérents et utiles.

---

## Soigner ses commits
- Comprendre l'historique du projet
- Faciliter le **revert**, le **cherry-pick**, la revue de code
- Générer des changelogs automatiques
- Rendre la collaboration plus fluide et la maintenance plus simple

---

## Commandes Git utiles

```bash
# Ajouter les modifications
git add fichier.txt
git add .

# Commit simple
git commit -m "message court"

# Commit multi-lignes
git commit

# Modifier le dernier commit
git commit --amend

# Historique compact
git log --oneline

# Voir les changements
git diff
git diff --staged

# Changer le message du dernier commit
git commit --amend -m "nouveau message"

# Commit signé (GPG)
git commit -S -m "message"

# Split interactif
git add -p
```

---

## Structure recommandée d’un message de commit

Une convention structurée permet d'uniformiser l'historique.

Structure recommandée :
<type>(<scope>): <titre court>

<description détaillée (optionnel)>

<footer(s) (optionnel): issues, breaking changes...>


- `type` : `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `style`, `init`, `ci`, ...
- `scope` : partie impactée (ex: `auth`, `api`, `ui`, `build`)
- `titre court` : impératif, ≤ 50 caractères recommandé
- `description` : expliquer le pourquoi + ce qui a été fait
- `footer` : références (ex: `Closes #123`), Breaking Changes (`BREAKING-CHANGE:`)

---

## Types et exemples précis

### `init`
Commit initial du projet ou d’une structure
init: initial commit - structure du projet

### `feat`
Nouvelle fonctionnalité
feat(api): ajout du endpoint GET /users

### `fix`
Correction de bug
fix(auth): corrige la validation du token expiré

### `docs`
Modifications de documentation
docs(readme): ajout des instructions d'installation sous Windows

### `style`
Changements de style sans impact logique (formatage)
style(css): correction indentations et normes linter

### `refactor`
Refactorisation sans changement de comportement
refactor(db): simplification du repository pattern

### `test`
Ajout/modification de tests
test(api): ajout test pour POST /orders

### `chore`
Maintenance sans impact fonctionnel : mises à jour de dépendances, nettoyage de configuration, modifications d'outils.
chore(debs): bump python3 to latest stable

### `ci`
CI/CD, pipelines
ci(github): ajout workflow build-and-test


---

## Règles pour le titre (ligne 1)
- Utiliser l’impératif présent : `Ajoute`, `Corrige` → formulaire recommandé : `feat(api): add pagination`
- Rester concis (idéalement ≤ 50 caractères)
- Ne pas terminer avec un point final
- Commencer par le type + scope optionnel
- Privilégier l'anglais

---

## Règles pour le corps du message (description)
- Expliquer **pourquoi** le changement a été fait (plus important que "quoi")
- Expliquer les conséquences ou choix techniques notables
- Mentionner les limitations connues et les points à vérifier
- Inclure des exemples d'utilisation si nécessaire

Exemple complet :
```bash
feat(payment): integration stripe checkout

Ajout d'un endpoint /checkout qui initialise une session Stripe.
La route renvoie l'URL de redirection pour le client.

Motivations :
Remplacer l'ancien système de paiement qui était obsolète.
Préparer les webhooks pour la gestion des paiements asynchrones.

Points à vérifier :
Clés Stripe en variable d'environnement
```

---

## Footer : issues et breaking changes
- Lier une issue : `Closes #123` ou `Fixes #123`
- Breaking change : inclure `BREAKING-CHANGE: description` dans le footer

Exemple :
```bash
refactor(api): change in response pattern

BREAKING-CHANGE: champ "userId" renommé en "idUser"
Closes: #789
```

---


## Bonnes pratiques

1. **Un changement = un commit**
	- Séparer fix, refactor, tests, docs

2. **Commits atomiques**
	- Facile à relire et revert
	- Merges propres

3. **Commit souvent, push intelligemment**
	- Commit local fréquent
	- Push après tests et nettoyage

4. **Ne pas réécrire l'historique partagé**
	- `git push --force` seulement si personne ne dépend de la branche
	- Préférer `--force-with-lease`

---

### Outils utiles

- **Commit-msg hook** : script dans `.git/hooks/` pour valider le format
- **Commitlint** : valider les messages
- **Template de commit** :
  - `git config --global commit.template ~/.gitmessage`
  - Exemple :
	 ```text
	 <type>(<scope>): <titre court>

	 Description (pourquoi) :
	 - point 1
	 - point 2

	 Footer:
	 Closes #NNN
	 BREAKING-CHANGE:
	 ```

### Exemples de commits

#### Commit initial du projet
```bash
init: initial project structure - add README, LICENSE, src/
```

#### Ajout d'une feature API
```bash
feat(api): add GET /users endpoint with pagination

Endpoint retourne la liste paginée d'utilisateurs.
Utilise les paramètres `page` et `per_page`.

Tests ajoutés : tests/api/users.test.js
```

#### Correction d’un bug critique
```bash
fix(auth): handle expired token errors gracefully

Ajout d'une vérification explicite pour token expiré afin de renvoyer 401
et message "token expired" au lieu d'exception 500.
```

#### Mise à jour de la doc
```bash
docs(contributing): add contribution guidelines and PR template

Inclut une section sur la convention de commit et le workflow Git.
```

#### Refactor important
```bash
refactor(db): move ORM layer to service folder

Aucun changement fonctionnel.
Prépare la séparation future entre services.
```

#### Tests
```bash
test(auth): add unit tests for token validation middleware
```

#### Chore (mise à jour dépendances)
```bash
chore(deps): upgrade eslint to 8.x and fix linter issues
```

## Checklist avant de push
- Tous les tests passent localement
- git status est propre (seulement les fichiers attendus en staged)
- Aucun secret committé (vérifier .env)
- Le message de commit est clair et suit la convention
- Si nécessaire, ajouter/mettre à jour la documentation
- Rebase ou merge local avec la branche cible (si policy) et résoudre les conflits

## Erreurs communes et comment les corriger

### Commit d'un secret
Supprimer le secret et réécrire l'historique (ex: git filter-repo ou git filter-branch), puis forcer le push
Informer l'équipe et invalider la clé/token compromis

### Séparer un gros commit en plusieurs
Utiliser git reset --soft HEAD~1 pour décomposer puis git add -p et re-commit en plusieurs commits

### Modifier un ancien commit (local)
git rebase -i <commit-before-target> puis modifier/rewriter
git push --force-with-lease si nécessaire (et sûr)

## Règles d'équipe recommandées
Adopter la convention
Valider les commit avec l'extension commitlint

## Conclusion

Soigner les commits est une pratique qui paye énormément sur le long terme : meilleure compréhension du projet, facilité de maintenance, automatisation des releases.
Adoptez une convention simple, appliquez-la avec des linters, et préférez des commits atomiques et bien rédigés.