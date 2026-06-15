import express, { json } from "express";
import { query } from './src/db/postgres.js';
import cors from "cors"

const app = express();

app.use(cors());
app.use(json());

// ─── Routes ─────────────────────────────────────────────────────────
app.get('/health', async (req, res) => {
  try {
    await query('SELECT 1 AS ok');

    console.log("/health succes : API et base de données opérationnelles")
    return res.status(200).json({
      status: 'healthy',
      uptime: process.uptime(),
      timestamp: new Date().toISOString(),
      database: 'connected',
      message: 'API et base de données opérationnelles'
    });
  } catch (err) {
    console.error('Health check failed:', err.message);

    return res.status(503).json({
      status: 'unhealthy',
      database: 'disconnected',
      message: 'Impossible de se connecter à la base de données',
      error: process.env.NODE_ENV === 'development' ? err.message : undefined
    });
  }
});

app.post('/sql', async (req, res) => {
  const { sql: sqlQuery, params = [] } = req.body;
  console.log( '/sql requete : ' + req)
  if (!sqlQuery || typeof sqlQuery !== 'string') {
    return res.status(400).json({
      error: 'Requête invalide',
      message: 'Le champ "sql" est requis et doit être une chaîne de caractères'
    });
    console.log('Le champ "sql" est requis et doit être une chaîne de caractères')
  }

  try {
    const result = await query(sqlQuery.trim(), params);

    console.log("/sql result :" + result)
    return res.status(200).json({
      success: true,
      rowCount: result.rowCount,
      rows: result.rows,
      fields: result.fields?.map(f => ({ name: f.name, dataTypeID: f.dataTypeID }))
    });

  } catch (err) {
    const pgErrors = {
      '42601': { status: 400, message: 'Erreur de syntaxe SQL' },
      '42P01': { status: 404, message: 'Table introuvable' },
      '42703': { status: 400, message: 'Colonne introuvable' },
      '23505': { status: 409, message: 'Violation de contrainte d\'unicité' },
      '23503': { status: 409, message: 'Violation de clé étrangère' },
      '23502': { status: 400, message: 'Violation de contrainte NOT NULL' },
      '28000': { status: 401, message: 'Authentification échouée' },
      '57014': { status: 408, message: 'Requête annulée (timeout)' },
    };

    const pgError = pgErrors[err.code];

    console.log("/sql erreur : " + pgError)

    return res.status(pgError?.status || 500).json({
      success: false,
      error: pgError?.message || 'Erreur serveur',
      ...(process.env.NODE_ENV === 'development' && {
        detail: err.message,
        code: err.code,
        hint: err.hint || undefined
      })
    });
  }
});

// 404 handler
app.use((req, res) => {
  console.log("Route non trouvée")
  res.status(404).json({ message: "Route non trouvée" });
});

// ─── Fonction d'attente de la base ──────────────────────────────────
async function waitForDatabase(maxAttempts = 30, delayMs = 2000) {
  console.log("Attente que PostgreSQL soit vraiment prêt...");

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const result = await query('SELECT 1 AS ok, version() AS pg_version');
      console.log(`PostgreSQL prêt après ${attempt} tentative(s)`);
      console.log("→ Version PostgreSQL :", result.rows[0].pg_version);
      return true;
    } catch (err) {
      console.log(`Tentative ${attempt}/${maxAttempts} → ${err.code || err.message}`);
      if (attempt === maxAttempts) {
        console.error("Échec définitif : PostgreSQL n'est pas accessible après plusieurs tentatives");
        process.exit(1); 
      }
      await new Promise(resolve => setTimeout(resolve, delayMs));
    }
  }
}

// ─── Démarrage du serveur ───────────────────────────────────────────
const PORT = process.env.PORT || 3000;
console.log("Defaut Port : " + process.env.PORT)
;(async () => {
  try {
    await waitForDatabase();

    app.listen(PORT, () => {
      console.log(`Serveur démarré → http://0.0.0.0:${PORT}`);
    });
  } catch (err) {
    console.error("Erreur fatale au démarrage :", err.message);
    process.exit(1);
  }
})();
