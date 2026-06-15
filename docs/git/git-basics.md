# Gestion basique de Git & GitHub + Utilisation avec VSCode

## Configuration initiale

### Définir son identité
```bash
git config --global user.name "Votre Nom"
git config --global user.email "email@example.com"
```

### Utiliser un token GitHub à la place du mot de passe
1. Créer un token : GitHub → Settings → Developer Settings → PAT
2. Dans un push :
   - Username : ton pseudo GitHub
   - Password : **le token**

#### Stocker le token (credential manager)
```bash
git config --global credential.helper store
```

---

## Commandes basiques Git

### Cloner un dépôt
```bash
git clone https://github.com/utilisateur/repo.git
```

### Vérifier les modifications
```bash
git status
```

### Ajouter un fichier
```bash
git add fichier.txt
```

### Ajouter tout
```bash
git add .
```

### Commit
```bash
git commit -m "Message"
```

### Push
```bash
git push
```

### Pull
```bash
git pull
```

---

## Gestion des branches

### Lister la branche active
```bash
git status
```

### Lister les branches
```bash
git branch
```

### Passer à une branche
```bash
git checkout nom-de-la-branche
```

---

## Utilisation avec VSCode

### 1. Vérifier la branche active
- En bas à gauche : **la branche active**
- Vérifier qu’elle correspond à celle de l’onglet *Source Control*

### 2. Changer de branche dans VSCode
- Cliquer sur le nom de la branche en bas → sélectionner la branche

### 3. Commit dans VSCode
- Onglet **Source Control**
- Saisir un message
- Cliquer **Commit**

### 4. Push / Pull
- Icônes dans la barre latérale Source Control
- Ou dans la barre en bas (petites flèches ↑ ↓)

### 5. Vérifier le GRAPH
- Onglet *Source Control* → *Repositories* → *Graph*
- IMPORTANT : Vérifier que le graph affiche **la même branche que celle active en bas**  

### 6. Résoudre les problèmes classiques
- Si un push échoue : faire un pull d’abord  
- Si la branche n’existe pas : cliquer *Publish Branch*

---