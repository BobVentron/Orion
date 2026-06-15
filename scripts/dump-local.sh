#!/bin/bash
# ============================================================
#  pg_dump_local.sh — Dump PostgreSQL depuis les containers
#  Docker de cette VM. À déposer et lancer directement sur
#  la machine qui héberge les containers.
#
#  Usage : ./pg_dump_local.sh
# ============================================================

set -euo pipefail

# ─────────────────────────────────────────────────────────────
#  CONFIGURATION DES PROJETS
#
#  Chaque entrée = un projet. Format du tableau :
#
#  PROJECTS+=("label|container|db|pg_user|source_mdp")
#
#  source_mdp : deux formes possibles
#   → env:/chemin/.env:NOM_VARIABLE    (lire depuis un .env)
#   → monmotdepasse                    (en dur en fallback)
#
#  Exemples concrets :
#   Orion (mdp dans .env)      : env:/etc/orion/.env:POSTGRES_PASSWORD
#   Projet avec mdp en clair   : postgres
# ─────────────────────────────────────────────────────────────

PROJECTS=()

# Orion — .env si présent, sinon fallback "admin"
PROJECTS+=("orion|orion_db|orion_db|orion_admin|env:/etc/orion/.env:POSTGRES_PASSWORD:admin")

# Projet avec mot de passe en dur (docker-compose hardcodé)
PROJECTS+=("orion2|orion_db|orion_db|admin|admin")

# ─────────────────────────────────────────────────────────────
#  RÉPERTOIRE DE SORTIE (sur cette VM)
# ─────────────────────────────────────────────────────────────
OUTPUT_DIR="./dumps/$(date +%Y-%m-%d_%H-%M-%S)"
mkdir -p "$OUTPUT_DIR"

# ─────────────────────────────────────────────────────────────
#  COULEURS
# ─────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}✓${NC} $*"; }
warn() { echo -e "  ${YELLOW}⚠${NC}  $*"; }
err()  { echo -e "  ${RED}✗${NC} $*"; }
info() { echo -e "  ${CYAN}→${NC} $*"; }

# ─────────────────────────────────────────────────────────────
#  RÉSOUDRE LE MOT DE PASSE
# ─────────────────────────────────────────────────────────────
resolve_password() {
    local spec="$1"
    local label="$2"

    # Cas 1 : env:/chemin/.env:NOM_VAR[:fallback]
    if [[ "$spec" == env:* ]]; then
        local env_path var_name fallback
        env_path=$(echo "$spec" | cut -d: -f2)
        var_name=$(echo "$spec"  | cut -d: -f3)
        fallback=$(echo "$spec"  | cut -d: -f4)   # vide si non fourni

        # .env absent → fallback si disponible, sinon prompt
        if [[ ! -f "$env_path" ]]; then
            if [[ -n "$fallback" ]]; then
                warn "$label : .env absent, utilisation du mot de passe en dur."
                echo "$fallback"
                return 0
            fi
            return 1   # déclenchera le prompt interactif
        fi

        # .env présent → lire la variable
        local pw
        pw=$(grep "^${var_name}=" "$env_path" \
             | cut -d= -f2- \
             | tr -d '"' \
             | tr -d "'" \
             | tr -d '[:space:]')

        if [[ -z "$pw" ]]; then
            if [[ -n "$fallback" ]]; then
                warn "$label : variable '$var_name' introuvable dans .env, utilisation du mot de passe en dur."
                echo "$fallback"
                return 0
            fi
            return 1
        fi

        echo "$pw"
        return 0
    fi

    # Cas 2 : mot de passe en dur directement
    echo "$spec"
}

# ─────────────────────────────────────────────────────────────
#  DUMP D'UN PROJET
# ─────────────────────────────────────────────────────────────
dump_project() {
    local entry="$1"
    IFS='|' read -r label container db pg_user pw_spec <<< "$entry"

    echo ""
    echo -e "  ┌─ ${CYAN}${label}${NC} (container: ${container})"

    # Vérifier que le container tourne
    local status
    status=$(docker inspect -f '{{.State.Status}}' "$container" 2>/dev/null || echo "missing")
    if [[ "$status" != "running" ]]; then
        err "container '$container' est '$status' — skipped."
        echo "  └─────"
        return 1
    fi

    # Résoudre le mot de passe
    local password
    if ! password=$(resolve_password "$pw_spec" "$label"); then
        # Fallback : demander interactivement
        echo -ne "  ${YELLOW}→ Mot de passe pour $label ($pg_user@$db) :${NC} "
        read -rs password
        echo ""
        if [[ -z "$password" ]]; then
            err "mot de passe vide — skipped."
            echo "  └─────"
            return 1
        fi
    fi

    # Lancer le dump
    local outfile="${OUTPUT_DIR}/${label}_${db}_$(date +%Y%m%d_%H%M%S).sql.gz"
    info "pg_dump → $(basename "$outfile")"

    if PGPASSWORD="$password" docker exec -i "$container" \
        pg_dump -U "$pg_user" -d "$db" -Fp --no-password \
        | gzip > "$outfile" 2>/tmp/pg_dump_err_${label}; then

        local size
        size=$(du -sh "$outfile" | cut -f1)
        ok "dump OK — $size"
        echo "  └─────"
        return 0
    else
        local errmsg
        errmsg=$(cat /tmp/pg_dump_err_${label} 2>/dev/null | tail -1)
        err "pg_dump échoué : $errmsg"
        rm -f "$outfile"
        echo "  └─────"
        return 1
    fi
}

# ─────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}╔══════════════════════════════════════╗${NC}"
echo -e "${CYAN}║       pg_dump_local — $(date +%H:%M:%S)       ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════╝${NC}"
echo -e "  Sortie : ${OUTPUT_DIR}"

success=0
failed=0

for entry in "${PROJECTS[@]}"; do
    if dump_project "$entry"; then
        ((success++)) || true
    else
        ((failed++))  || true
    fi
done

echo ""
echo -e "${CYAN}══════════════════════════════════════${NC}"
echo -e "  ${GREEN}${success} OK${NC}  /  ${RED}${failed} erreur(s)${NC}"
echo -e "  Dumps : ${OUTPUT_DIR}"
echo -e "${CYAN}══════════════════════════════════════${NC}"
echo ""

[ "$failed" -eq 0 ]
