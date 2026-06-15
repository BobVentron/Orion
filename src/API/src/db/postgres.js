import { Pool } from 'pg';

export const db = new Pool({
  host: process.env.POSTGRES_HOST|| 'db',
  port: Number(process.env.POSTGRES_PORT) || 5432,
  database: process.env.POSTGRES_DB || 'orion_db',
  user: process.env.POSTGRES_USER || 'orion_admin',
  password: process.env.POSTGRES_PASSWORD,
  rejectUnauthorized: false 
});

export const query = (text, params) => db.query(text, params);