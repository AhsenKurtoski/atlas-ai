/**
 * Configurazione del frontend ATLAS AI.
 *
 * Priorità per l'URL del backend:
 *   1. EXPO_PUBLIC_API_URL (build production / staging)
 *   2. IP LAN di Expo Go (stessa rete del PC)
 *   3. Loopback: 10.0.2.2 su emulatore Android, localhost altrove
 */
import Constants from 'expo-constants';
import { Platform } from 'react-native';

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

  // L'emulatore Android raggiunge il PC host tramite 10.0.2.2.
  if (Platform.OS === 'android') {
    return 'http://10.0.2.2:8000';
  }
  return 'http://localhost:8000';
}

export const CONFIG = {
  API_URL: getApiUrl(),
  APP_NAME: 'ATLAS AI',
  STORAGE_AUTH_TOKEN_KEY: '@atlas/auth_token',
  STORAGE_PROFILE_KEY: '@atlas/profile',
  STORAGE_PROFILE_INFO_KEY: '@atlas/profile_info',
  MIN_PIN_LENGTH: 4,
  MAX_PIN_LENGTH: 8,
  REQUEST_TIMEOUT_MS: 15000,
};

export default CONFIG;
