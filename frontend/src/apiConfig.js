// In development, when VITE_API_URL is unset, this evaluates to "" (empty string),
// which routes through Vite's local dev proxy defined in vite.config.js.
// In production (e.g., hosted on Vercel), set VITE_API_URL to your deployed backend
// URL (e.g. "https://invoice-ai-backend.onrender.com").
export const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/+$/, '');
