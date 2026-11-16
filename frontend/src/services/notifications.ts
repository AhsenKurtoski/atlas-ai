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
const REMINDER_IDS_KEY = '@atlas/reminder_notifications';
const ENABLED_KEY = '@atlas/notifications_enabled';
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

/** Mostra subito una notifica locale reale (utile per verificare i permessi). */
export async function sendLocalTestNotification(): Promise<boolean> {
  if (Platform.OS === 'web') return false;
  try {
    const granted = await ensureNotificationPermission();
    if (!granted) return false;
    await Notifications.scheduleNotificationAsync({
      content: {
        title: '🔔 Test ATLAS',
        body: 'Le notifiche locali funzionano su questo dispositivo.',
        sound: 'default',
        data: { tipo: 'test_locale' },
      },
      trigger: null,
    });
    return true;
  } catch {
    return false;
  }
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
  await AsyncStorage.setItem(ENABLED_KEY, enabled ? '1' : '0').catch(() => {});
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
        trigger: {
          hour: reminder.hour,
          minute: reminder.minute,
          repeats: true,
          channelId: CHANNEL_ID,
        } as any,
      });
      ids.push(id);
    } catch {
      // Un promemoria non pianificato non blocca gli altri.
    }
  }
  await AsyncStorage.setItem(LOCAL_IDS_KEY, JSON.stringify(ids));
}

/** Rispetta la scelta salvata dall'utente (default: attive al primo avvio). */
export async function syncLocalRemindersFromPreference(): Promise<void> {
  const stored = await AsyncStorage.getItem(ENABLED_KEY).catch(() => null);
  await syncLocalReminders(stored !== '0');
}

/** Allinea i promemoria giornalieri alla impostazione condivisa del backend. */
export async function syncLocalRemindersFromSettings(): Promise<void> {
  try {
    const response = await apiService.getSettings();
    const enabled = response.data?.notifiche?.attive;
    if (typeof enabled === 'boolean') {
      await syncLocalReminders(enabled);
      return;
    }
  } catch {
    // Offline o token non ancora disponibile: usa la preferenza del dispositivo.
  }
  await syncLocalRemindersFromPreference();
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

// ---------------- Promemoria personali della chat ----------------

interface ScheduledReminderLink {
  reminderId: string;
  notificationId: string;
}

export interface ReminderSyncResult {
  ok: boolean;
  scheduled: number;
  message: string;
}

async function cancelReminderNotifications(): Promise<void> {
  try {
    const raw = await AsyncStorage.getItem(REMINDER_IDS_KEY);
    const links: ScheduledReminderLink[] = raw ? JSON.parse(raw) : [];
    await Promise.all(
      links.map((link) =>
        Notifications.cancelScheduledNotificationAsync(link.notificationId).catch(() => {})
      )
    );
  } catch {
    // Nessun promemoria personalizzato salvato.
  } finally {
    await AsyncStorage.removeItem(REMINDER_IDS_KEY).catch(() => {});
  }
}

/** Annulla solo le notifiche dei promemoria creati dalla chat. */
export async function cancelUpcomingReminderNotifications(): Promise<void> {
  if (Platform.OS === 'web') return;
  await cancelReminderNotifications();
}

/**
 * Sincronizza i promemoria futuri dal backend e li pianifica come notifiche
 * locali reali. Funziona anche se l'app viene chiusa e non richiede EAS/FCM.
 * La conferma al backend evita che lo scheduler invii anche una push duplicata.
 */
export async function syncUpcomingReminders(): Promise<ReminderSyncResult> {
  if (Platform.OS === 'web') {
    return { ok: false, scheduled: 0, message: 'Le notifiche locali non sono disponibili sul web.' };
  }

  const enabled = await AsyncStorage.getItem(ENABLED_KEY).catch(() => null);
  if (enabled === '0') {
    await cancelReminderNotifications();
    return {
      ok: true,
      scheduled: 0,
      message: 'Notifiche disattivate: riattivale da Impostazioni per ricevere i promemoria.',
    };
  }

  let rows: any[] = [];
  try {
    const response = await apiService.getReminders();
    rows = response.data ?? [];
  } catch (error: any) {
    return {
      ok: false,
      scheduled: 0,
      message: error?.message ?? 'Promemoria non scaricati dal backend.',
    };
  }

  if (!rows.length) {
    await cancelReminderNotifications();
    return { ok: true, scheduled: 0, message: 'Nessun promemoria futuro da programmare.' };
  }

  const granted = await ensureNotificationPermission();
  if (!granted) {
    return {
      ok: false,
      scheduled: 0,
      message: 'Permesso notifiche negato: il promemoria resta nella lista, ma non può avvisarti.',
    };
  }

  // Solo dopo aver letto i dati annulliamo le vecchie pianificazioni: un errore
  // di rete non deve far perdere i promemoria già presenti sul dispositivo.
  await cancelReminderNotifications();
  const links: ScheduledReminderLink[] = [];
  let skipped = 0;

  for (const row of rows) {
    const when = new Date(String(row?.remind_at ?? ''));
    if (!row?.id || Number.isNaN(when.getTime()) || when.getTime() <= Date.now()) {
      skipped += 1;
      continue;
    }
    const lista: string[] = Array.isArray(row.lista) ? row.lista : [];
    let body = String(row.message ?? 'Promemoria ATLAS');
    if (row.include_todos && lista.length) {
      const anteprima = lista.slice(0, 12).join(', ');
      body += `\n🛒 Lista (${lista.length}): ${anteprima}${lista.length > 12 ? '…' : ''}`;
    }
    try {
      const notificationId = await Notifications.scheduleNotificationAsync({
        content: {
          title: row.include_todos ? '🛒 Promemoria spesa' : '⏰ Promemoria ATLAS',
          body: body.slice(0, 800),
          sound: 'default',
          data: { tipo: 'promemoria', reminder_id: String(row.id) },
        },
        trigger: { date: when, channelId: CHANNEL_ID } as any,
      });
      links.push({ reminderId: String(row.id), notificationId });
      await apiService.markReminderLocalScheduled(String(row.id)).catch(() => {});
    } catch {
      skipped += 1;
    }
  }

  if (links.length) {
    await AsyncStorage.setItem(REMINDER_IDS_KEY, JSON.stringify(links));
  }
  return {
    ok: true,
    scheduled: links.length,
    message:
      links.length > 0
        ? `${links.length} promemoria programmati sul dispositivo.`
        : skipped > 0
          ? 'Alcuni promemoria sono già scaduti o non pianificabili.'
          : 'Nessun promemoria futuro da programmare.',
  };
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
