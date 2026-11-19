/**
 * Configurazione del frontend ATLAS AI.
 *
 * Priorità per l'URL del backend:
 *   1. EXPO_PUBLIC_API_URL (build production / staging)
 *   2. Web (browser e web app servita dal PC): stesso host della pagina, così
 *      l'IP della LAN può cambiare senza ricostruire il bundle
 *   3. IP LAN di Expo Go (stessa rete del PC)
 *   4. Loopback: 10.0.2.2 su emulatore Android, localhost altrove
 */
import Constants from 'expo-constants';
import { Platform } from 'react-native';

export function getApiUrl(): string {
  const envUrl = process.env.EXPO_PUBLIC_API_URL;
  if (envUrl) {
    return envUrl.replace(/\/$/, '');
  }

  // Web: la pagina è servita dal PC (o dall'emulatore) e il backend gira sullo
  // stesso host. `EXPO_PUBLIC_BACKEND_PORT` copre installazioni su altra porta;
  // il default 8010 è quello di `start-atlas.bat`, 8000 quello di `expo start`.
  const webLocation = (globalThis as any)?.location;
  if (Platform.OS === 'web' && webLocation?.hostname) {
    const host = webLocation.hostname;
    const pagePort = String(webLocation.port || '');
    const fallbackPort = pagePort === '8081' ? '8000' : '8010';
    const port = process.env.EXPO_PUBLIC_BACKEND_PORT || fallbackPort;
    return `http://${host}:${port}`;
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
  BACKEND_PORT: process.env.EXPO_PUBLIC_BACKEND_PORT || '8010',
  APP_NAME: 'ATLAS AI',
  STORAGE_AUTH_TOKEN_KEY: '@atlas/auth_token',
  STORAGE_PROFILE_KEY: '@atlas/profile',
  STORAGE_PROFILE_INFO_KEY: '@atlas/profile_info',
  MIN_PIN_LENGTH: 4,
  MAX_PIN_LENGTH: 8,
  REQUEST_TIMEOUT_MS: 15000,
  // Dopo quanti minuti senza attività l'app si richiude sul PIN, anche se il
  // telefono è rimasto in foreground o è tornato dal blocco schermo.
  AUTO_LOCK_MINUTES: 5,
  // Quante voci del registro accessi mostrare in Impostazioni.
  ACCESS_LOG_LIMIT: 20,
};

export default CONFIG;
