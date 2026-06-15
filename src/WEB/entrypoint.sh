#!/bin/sh
# ───────────────────────────────────────────────────────────────
# entrypoint.sh – lancé au démarrage du conteneur web (en root)
#
# Rôle : s'assurer qu'un certificat SSL est toujours présent dans
# /etc/nginx/ssl/ avant de démarrer nginx.
#
# Cas 1 : le volume docker-compose monte /etc/orion/ssl/ (cert généré
#         par orion-control) → les fichiers sont déjà là, on ne touche à rien.
# Cas 2 : le volume est vide ou absent (premier démarrage sans orion-control,
#         test d'image…) → on copie le cert de secours intégré à l'image
#         depuis /etc/nginx/ssl-builtin/.
# ───────────────────────────────────────────────────────────────
set -e

SSL_DIR="/etc/nginx/ssl"
BUILTIN_DIR="/etc/nginx/ssl-builtin"

if [ ! -f "${SSL_DIR}/orion.crt" ] || [ ! -f "${SSL_DIR}/orion.key" ]; then
    echo "[Orion] Aucun certificat trouvé dans ${SSL_DIR}/"
    echo "[Orion] → Utilisation du certificat de secours intégré à l'image."
    mkdir -p "${SSL_DIR}"
    cp "${BUILTIN_DIR}/orion.crt" "${SSL_DIR}/orion.crt"
    cp "${BUILTIN_DIR}/orion.key" "${SSL_DIR}/orion.key"
    chmod 600 "${SSL_DIR}/orion.key"
    chmod 644 "${SSL_DIR}/orion.crt"
else
    echo "[Orion] Certificat SSL trouvé dans ${SSL_DIR}/ → utilisation."
fi

exec nginx -g "daemon off;"
