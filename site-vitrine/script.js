const API_URL = "http://localhost:3000/health";

const statusCard     = document.getElementById("status-card");
const statusTitle    = document.getElementById("status-title");
const statusMessage  = document.getElementById("status-message");
const indicator      = document.getElementById("indicator");
const lastCheck      = document.getElementById("last-check");
const refreshBtn     = document.getElementById("refresh");

async function checkHealth() {
  const now = new Date().toLocaleTimeString("fr-FR", { hour12: false });
  lastCheck.textContent = now;

  statusCard.className = "status-card checking";
  statusTitle.textContent = "Vérification...";
  statusMessage.textContent = "Connexion à l’API...";

  try {
    const response = await fetch(API_URL, {
      cache: "no-store",
      headers: { "Cache-Control": "no-cache" }
    });

    if (!response.ok) {
      throw new Error(`Statut HTTP ${response.status}`);
    }

    const data = await response.json();

    // Mise à jour de l'affichage selon le statut reçu
    if (data.status === "healthy") {
      statusCard.className = "status-card healthy";
      statusTitle.textContent = "Service opérationnel";
      statusMessage.textContent = data.message || "Base de données connectée";
    } else {
      statusCard.className = "status-card unhealthy";
      statusTitle.textContent = "Service dégradé";
      statusMessage.textContent = data.message || "Problème détecté";
    }

  } catch (error) {
    statusCard.className = "status-card unhealthy";
    statusTitle.textContent = "Erreur de connexion";
    statusMessage.textContent =
      error.message.includes("fetch")
        ? "Impossible de joindre l’API (serveur arrêté ? CORS ?)"
        : error.message;
  }
}

checkHealth();

// Bouton rafraîchir
refreshBtn.addEventListener("click", checkHealth);