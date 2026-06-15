#!/bin/bash
set -e

# Plus de pip install ici — le package n'est pas installé en mode editable.
# Python trouve orion_scanner/ grâce à PYTHONPATH=/app (défini dans le Dockerfile),
# qui pointe sur le volume ./poller/src monté dans /app.
#
# Vérification rapide au démarrage pour diagnostiquer les problèmes de montage.
if [ ! -d /app/orion_scanner ]; then
    echo "ERREUR : /app/orion_scanner introuvable."
    echo "Vérifiez que le volume './poller/src:/app' est bien monté dans docker-compose.yml"
    exit 1
fi

echo "orion_scanner trouvé dans /app — démarrage."

# Exécute la commande passée en argument (CMD = /bin/bash par défaut)
exec "$@"
