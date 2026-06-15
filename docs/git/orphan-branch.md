# Création d’une branche orpheline

---

## Branche orpheline

Une **branche orpheline** est une branche **qui ne possède aucun lien avec l’historique du projet**.
Elle démarre sans commit parent → comme un dépôt totalement neuf à l’intérieur du même repository.

### À quoi ça sert réellement ?
Une branche orpheline est utile lorsque l’on souhaite **segmenter complètement un projet**, par exemple :

- séparer la **documentation** du code source principal
- isoler **serveur**, **frontend**, **API**, **scripts Python**, etc. dans leur propre historique
- regrouper un ensemble de fichiers qui **ne doivent pas être mélangés** au reste du repository
- éviter que des parties du projet soient polluées par les commits, fichiers, dossiers ou dépendances d’une autre partie
- créer des zones indépendantes dans un même repo lorsque tout ne fonctionne pas ensemble, mais que l’on veut **regrouper le tout dans un seul repository GitHub**

---

## Créer une branche orpheline

```bash
# Se positionner sur main
git checkout main

# Créer une branche orpheline sans historique
git checkout --orphan nom-de-la-branche

# Supprimer les fichiers hérités
git rm -rf .

# Ajouter un fichier initial
echo "# Nouveau contenu indépendant" > README.md

# Ajouter et commit
git add .
git commit -m "Initialisation de la branche orpheline"

# Envoyer au dépôt
git push origin nom-de-la-branche
```

---

## Commandes associées

### Supprimer une branche locale
```bash
git branch -D nom-de-la-branche
```

### Supprimer une branche distante
```bash
git push origin --delete nom-de-la-branche
```

### Revenir sur main
```bash
git checkout main
```

---