/**
 * Configurazione dinamica del frontend ATLAS AI.
 *
 * Priorità per determinare l'URL del backend:
 *   1. Variabile ambiente EXPO_PUBLIC_API_URL (se impostata in .env)
 *   2. Constants.expoConfig?.hostUri (Expo Go: IP LAN + porta 8000)
 *   3. http://localhost:8000 (web/desktop)
 */
import Constants from 'expo-constants';

export function getApiUrl(): string {
  const envUrl = process.env.EXPO_PUBLIC_API_URL;
  if (envUrl) {
    return envUrl.replace(/\/$/, '');
  }

  const hostUri = Constants.expoConfig?.hostUri;
  if (hostUri) {
    const host = hostUri.split(':')[0];
    if (host && host !== 'localhost' && host !== '127.0.0.1') {
      return `http://${host}:8000`;
    }
  }

  return 'http://localhost:8000';
}

export const CONFIG = {
  API_URL: getApiUrl(),
  STORAGE_AUTH_TOKEN_KEY: '@atlas/auth_token',
  STORAGE_PROFILE_KEY: '@atlas/profile',
  MAX_PIN_LENGTH: 4,
  REQUEST_TIMEOUT_MS: 15000,
};

export default CONFIG;
