/**
 * Notifiche di ATLAS AI.
 *
 * Due canali, entrambi reali e gratuiti:
 *  1. **Locali** (expo-notifications): promemoria giornalieri pianificati sul
 *     dispositivo, funzionano anche senza backend e senza account.
 *  2. **Remote push** (Expo Push Service): il token del dispositivo viene
 *     registrato sul backend e le automazioni possono inviare notifiche.
 *     Richiede il `projectId` EAS in app.json (`extra.eas.projectId`).
 *
 * Nessuna simulazione: se il token non è disponibile viene restituito il
 * motivo esatto e le notifiche locali restano attive.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from 'expo-constants';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';
import apiService from './api';

const PUSH_TOKEN_KEY = '@atlas/push_token';
const LOCAL_IDS_KEY = '@atlas/local_notifications';
const CHANNEL_ID = 'atlas_default';

export interface PushRegistration {
  ok: boolean;
  token?: string;
  message: string;
}

/** Configura come mostrare le notifiche quando l'app è in foreground. */
export function configureNotifications(): void {
  if (Platform.OS === 'web') return;
  try {
    Notifications.setNotificationHandler({
    handleNotification: async () =>
      ({
        shouldShowAlert: true,
        shouldPlaySound: true,
        shouldSetBadge: false,
        shouldShowBanner: true,
        shouldShowList: true,
        } as any),
    });
  } catch {
    // Piattaforma senza supporto notifiche: l'app resta utilizzabile.
  }
}

async function ensureAndroidChannel(): Promise<void> {
  if (Platform.OS !== 'android') return;
  try {
    await Notifications.setNotificationChannelAsync(CHANNEL_ID, {
      name: 'ATLAS',
      importance: Notifications.AndroidImportance.HIGH,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: '#7c3aed',
    });
  } catch {
    // Canale già presente o permessi mancanti: non blocca il flusso.
  }
}

export async function ensureNotificationPermission(): Promise<boolean> {
  await ensureAndroidChannel();
  const current = await Notifications.getPermissionsAsync();
  if (current.granted) return true;
  if (!current.canAskAgain) return false;
  const requested = await Notifications.requestPermissionsAsync();
  return requested.granted;
}

function projectId(): string | undefined {
  const extra = Constants.expoConfig?.extra as any;
  return extra?.eas?.projectId ?? (Constants as any).easConfig?.projectId ?? undefined;
}

/** Registra il dispositivo sul backend (Expo Push Service). */
export async function registerPushToken(profileId: string): Promise<PushRegistration> {
  if (Platform.OS === 'web') {
    return { ok: false, message: 'Le notifiche push non sono disponibili nella preview web.' };
  }
  if (!Device.isDevice) {
    return { ok: false, message: 'Le notifiche push richiedono un dispositivo fisico.' };
  }

  const granted = await ensureNotificationPermission();
  if (!granted) {
    return {
      ok: false,
      message: 'Permesso notifiche negato: attivalo dalle impostazioni di sistema dell\'app.',
    };
  }

  const id = projectId();
  if (!id) {
    return {
      ok: false,
      message:
        'Manca il projectId EAS in app.json (extra.eas.projectId): i promemoria locali funzionano, ' +
        'le push remote no. Esegui `eas init` e riavvia l\'app.',
    };
  }

  try {
    const tokenResponse = await Notifications.getExpoPushTokenAsync({ projectId: id });
    const token = tokenResponse.data;
    if (!token) {
      return { ok: false, message: 'Token push non ottenuto dal sistema.' };
    }
    await apiService.registerPushToken({
      token,
      device: `${Device.modelName ?? 'Dispositivo'} ${Device.osName ?? ''}`.trim(),
      platform: Platform.OS,
    });
    await AsyncStorage.setItem(PUSH_TOKEN_KEY, token);
    return { ok: true, token, message: 'Notifiche push attive su questo dispositivo.' };
  } catch (error: any) {
    return {
      ok: false,
      message: error?.message ?? 'Registrazione push non riuscita.',
    };
  }
}

/** Rimuove il token dal backend (logout o disattivazione). */
export async function unregisterPushToken(): Promise<void> {
  try {
    const token = await AsyncStorage.getItem(PUSH_TOKEN_KEY);
    if (token) {
      await apiService.unregisterPushToken(token);
    }
  } catch {
    // Offline: il token scadrà lato Expo automaticamente.
  } finally {
    await AsyncStorage.removeItem(PUSH_TOKEN_KEY);
  }
}

// ---------------- Promemoria locali ----------------

interface ReminderSpec {
  key: string;
  hour: number;
  minute: number;
  title: string;
  body: string;
}

const REMINDERS: ReminderSpec[] = [
  { key: 'lezione_matina', hour: 7, minute: 30, title: '📚 Lezione di italiano', body: 'Cinque minuti di italiano oggi? Apri ATLAS.' },
  { key: 'acqua_mattina', hour: 10, minute: 0, title: '💧 Bevi un bicchiere d\'acqua', body: 'Una piccola pausa per la famiglia.' },
  { key: 'acqua_pomeriggio', hour: 15, minute: 0, title: '💧 Pausa idratazione', body: 'Ricordati di bere: fa bene a tutti.' },
  { key: 'acqua_sera', hour: 19, minute: 0, title: '💧 Acqua della sera', body: 'Un bicchiere d\'acqua prima di cena.' },
];

/** Pianifica i promemoria locali (idempotente: cancella i precedenti). */
export async function syncLocalReminders(enabled: boolean): Promise<void> {
  await cancelLocalReminders();
  if (!enabled) return;

  const granted = await ensureNotificationPermission();
  if (!granted) return;

  const ids: string[] = [];
  for (const reminder of REMINDERS) {
    try {
      const id = await Notifications.scheduleNotificationAsync({
        content: {
          title: reminder.title,
          body: reminder.body,
          sound: 'default',
          data: { tipo: 'promemoria_locale', chiave: reminder.key },
        },
        trigger: { hour: reminder.hour, minute: reminder.minute, repeats: true } as any,
      });
      ids.push(id);
    } catch {
      // Un promemoria non pianificato non blocca gli altri.
    }
  }
  await AsyncStorage.setItem(LOCAL_IDS_KEY, JSON.stringify(ids));
}

export async function cancelLocalReminders(): Promise<void> {
  try {
    const raw = await AsyncStorage.getItem(LOCAL_IDS_KEY);
    const ids: string[] = raw ? JSON.parse(raw) : [];
    await Promise.all(ids.map((id) => Notifications.cancelScheduledNotificationAsync(id).catch(() => {})));
  } catch {
    // Nessun promemoria salvato.
  } finally {
    await AsyncStorage.removeItem(LOCAL_IDS_KEY);
  }
}

/** Numero di notifiche locali pianificate (utile per il debug in Impostazioni). */
export async function scheduledRemindersCount(): Promise<number> {
  try {
    const scheduled = await Notifications.getAllScheduledNotificationsAsync();
    return scheduled.length;
  } catch {
    return 0;
  }
}
