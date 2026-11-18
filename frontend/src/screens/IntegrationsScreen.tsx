import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  Switch,
  TouchableOpacity,
  ScrollView,
  SafeAreaView,
  TextInput,
  Alert,
  Linking,
  ActivityIndicator,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import apiService, { AppSettings, GoogleStatus, ProfileRow, ReminderRow } from '../services/api';
import {
  registerPushToken,
  unregisterPushToken,
  syncLocalReminders,
  syncUpcomingReminders,
  cancelUpcomingReminderNotifications,
  sendLocalTestNotification,
  scheduledRemindersCount,
} from '../services/notifications';
import { useAuth } from '../../App';
import CONFIG from '../config';

const LIVELLI = ['A1', 'A2', 'B1', 'B2', 'C1'];

export default function IntegrationsScreen() {
  const navigation = useNavigation<any>();
  const { profileId, profile, clearAuth } = useAuth();
  const isAdmin = profileId === 'io';

  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [google, setGoogle] = useState<GoogleStatus | null>(null);
  const [profiles, setProfiles] = useState<Record<string, ProfileRow>>({});
  const [devices, setDevices] = useState(0);
  const [reminders, setReminders] = useState<ReminderRow[]>([]);
  const [scheduled, setScheduled] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  const [showAddProfile, setShowAddProfile] = useState(false);
  const [newNome, setNewNome] = useState('');
  const [newPin, setNewPin] = useState('');
  const [newLivello, setNewLivello] = useState('B1');

  const load = useCallback(async () => {
    const [settingsResult, googleResult, profilesResult, dashboardResult, remindersResult] = await Promise.allSettled([
      apiService.getSettings(),
      apiService.getGoogleStatus(),
      apiService.getProfiles(),
      apiService.getDashboard(),
      apiService.getReminders(),
    ]);

    if (settingsResult.status === 'fulfilled' && settingsResult.value.data) {
      setSettings(settingsResult.value.data);
    }
    if (googleResult.status === 'fulfilled' && googleResult.value.data) {
      setGoogle(googleResult.value.data);
    }
    if (profilesResult.status === 'fulfilled' && profilesResult.value) {
      setProfiles(profilesResult.value);
    }
    if (dashboardResult.status === 'fulfilled' && dashboardResult.value.data) {
      setDevices(dashboardResult.value.data.dispositivi_notifiche);
    }
    if (remindersResult.status === 'fulfilled' && Array.isArray(remindersResult.value.data)) {
      setReminders(remindersResult.value.data);
    } else {
      setReminders([]);
    }
    setScheduled(await scheduledRemindersCount());
    setLoading(false);
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  // Ritorno dal flusso OAuth Google (deep link atlasai://oauth?...).
  useEffect(() => {
    const subscription = Linking.addEventListener('url', ({ url }) => {
      if (url.includes('oauth')) {
        load();
        Alert.alert(
          'Google',
          url.includes('google=ok')
            ? 'Account collegato! Gmail e Calendar sono ora disponibili in chat.'
            : 'Collegamento non completato. Riprova da Impostazioni.'
        );
      }
    });
    return () => subscription.remove();
  }, [load]);

  const automation = (key: string): boolean => settings?.automazioni?.[key] ?? true;
  const notificationsOn = settings?.notifiche?.attive ?? true;

  const toggleAutomation = async (key: string, value: boolean) => {
    if (!settings) return;
    const previous = settings;
    setSettings({
      ...settings,
      automazioni: { ...settings.automazioni, [key]: value },
    });
    try {
      const response = await apiService.updateSettings({ automazioni: { [key]: value } });
      if (response.data) setSettings(response.data);
    } catch (error: any) {
      setSettings(previous);
      Alert.alert('Errore', error?.message ?? 'Impostazione non salvata.');
    }
  };

  const toggleNotifications = async (value: boolean) => {
    if (!settings) return;
    const previous = settings;
    setSettings({ ...settings, notifiche: { ...settings.notifiche, attive: value } });
    try {
      const response = await apiService.updateSettings({ notifiche: { attive: value } });
      if (response.data) setSettings(response.data);

      if (value) {
        await syncLocalReminders(true);
        const registration = await registerPushToken(profileId ?? 'io');
        await syncUpcomingReminders();
        Alert.alert(
          registration.ok ? 'Notifiche attive' : 'Promemoria locali attivi',
          registration.message
        );
      } else {
        await syncLocalReminders(false);
        await unregisterPushToken();
        await cancelUpcomingReminderNotifications();
      }
      setScheduled(await scheduledRemindersCount());
    } catch (error: any) {
      setSettings(previous);
      Alert.alert('Errore', error?.message ?? 'Impossibile aggiornare le notifiche.');
    }
  };

  const cancelReminder = (reminder: ReminderRow) => {
    Alert.alert('Annullare il promemoria?', reminder.message, [
      { text: 'No', style: 'cancel' },
      {
        text: 'Annulla promemoria',
        style: 'destructive',
        onPress: async () => {
          try {
            await apiService.cancelReminder(reminder.id);
            await syncUpcomingReminders();
            await load();
          } catch (error: any) {
            Alert.alert('Errore', error?.message ?? 'Promemoria non annullato.');
          }
        },
      },
    ]);
  };

  const formatReminderTime = (value: string): string => {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString('it-IT', {
      weekday: 'short',
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const sendTest = async () => {
    setBusy('test');
    try {
      const response = await apiService.sendTestNotification();
      if (response.status === 'ok') {
        Alert.alert('Inviata', response.message ?? '');
      } else if (await sendLocalTestNotification()) {
        Alert.alert('Notifica locale inviata', 'Controlla il centro notifiche del dispositivo.');
      } else {
        Alert.alert('Attenzione', response.message ?? 'Nessun canale notifiche disponibile.');
      }
    } catch (error: any) {
      if (await sendLocalTestNotification()) {
        Alert.alert('Notifica locale inviata', 'Controlla il centro notifiche del dispositivo.');
      } else {
        Alert.alert('Errore', error?.message ?? 'Invio non riuscito.');
      }
    } finally {
      setBusy(null);
    }
  };

  const connectGoogle = async () => {
    if (!google?.configurato) {
      Alert.alert(
        'Integrazione Google non configurata',
        google?.istruzioni ||
          'Imposta GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET nel backend/.env (credenziali gratuite su console.cloud.google.com).'
      );
      return;
    }
    if (google.connesso) {
      Alert.alert('Google collegato', google.email || 'Account collegato', [
        { text: 'Chiudi', style: 'cancel' },
        {
          text: 'Scollega',
          style: 'destructive',
          onPress: async () => {
            try {
              await apiService.disconnectGoogle();
              await load();
            } catch (error: any) {
              Alert.alert('Errore', error?.message ?? 'Scollegamento non riuscito.');
            }
          },
        },
      ]);
      return;
    }
    setBusy('google');
    try {
      const response = await apiService.getGoogleAuthUrl();
      const url = response.data?.url;
      if (response.status !== 'ok' || !url) {
        Alert.alert('Integrazione Google', response.message || 'URL di autorizzazione non disponibile.');
        return;
      }
      await Linking.openURL(url);
    } catch (error: any) {
      Alert.alert('Errore', error?.message ?? 'Impossibile aprire il consenso Google.');
    } finally {
      setBusy(null);
    }
  };

  const createProfile = async () => {
    if (!newNome.trim()) {
      Alert.alert('Nome mancante', 'Inserisci il nome del membro della famiglia.');
      return;
    }
    if (!/^\d{4,8}$/.test(newPin)) {
      Alert.alert('PIN non valido', 'Il PIN deve essere di 4-8 cifre.');
      return;
    }
    setBusy('profilo');
    try {
      const response = await apiService.createProfile({
        nome: newNome.trim(),
        pin: newPin,
        livello_italiano: newLivello,
      });
      if (response.status !== 'ok') {
        Alert.alert('Profilo non creato', response.message ?? 'Errore sconosciuto.');
        return;
      }
      setNewNome('');
      setNewPin('');
      setNewLivello('B1');
      setShowAddProfile(false);
      await load();
      Alert.alert('Profilo creato', response.message ?? 'Ora può accedere con il suo PIN.');
    } catch (error: any) {
      Alert.alert('Errore', error?.message ?? 'Creazione non riuscita.');
    } finally {
      setBusy(null);
    }
  };

  const deleteProfile = (slug: string, nome: string) => {
    Alert.alert('Eliminare il profilo?', `${nome} non potrà più accedere con il suo PIN.`, [
      { text: 'Annulla', style: 'cancel' },
      {
        text: 'Elimina',
        style: 'destructive',
        onPress: async () => {
          try {
            const response = await apiService.deleteProfile(slug);
            if (response.status !== 'ok') {
              Alert.alert('Non eliminato', response.message ?? '');
              return;
            }
            await load();
          } catch (error: any) {
            Alert.alert('Errore', error?.message ?? 'Eliminazione non riuscita.');
          }
        },
      },
    ]);
  };

  const logout = () => {
    Alert.alert('Uscire da ATLAS?', 'Dovrai reinserire il PIN per rientrare.', [
      { text: 'Annulla', style: 'cancel' },
      { text: 'Esci', style: 'destructive', onPress: () => clearAuth() },
    ]);
  };

  const row = (icon: string, title: string, description: string, value: boolean, onChange: (next: boolean) => void, color = '#7c3aed') => (
    <View className="bg-[rgba(255,255,255,0.06)] p-5 rounded-3xl mb-4 flex-row justify-between items-center border border-white/5">
      <View className="flex-1 pr-4">
        <Text className="text-white text-xl font-bold">
          {icon} {title}
        </Text>
        <Text className="text-gray-400 mt-1">{description}</Text>
      </View>
      <Switch
        value={value}
        onValueChange={onChange}
        trackColor={{ false: '#333', true: color }}
        thumbColor="#fff"
      />
    </View>
  );

  if (loading) {
    return (
      <SafeAreaView className="flex-1 bg-[#0a0a0f] items-center justify-center">
        <StatusBar style="light" />
        <ActivityIndicator color="#7c3aed" size="large" />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView className="flex-1 bg-[#0a0a0f]">
      <StatusBar style="light" />
      <ScrollView className="flex-1 p-5">
        <Text className="text-4xl font-extrabold text-white mb-2 mt-4">Hub Automazioni</Text>
        <Text className="text-gray-400 mb-8">
          {profile?.nome ?? profileId} · livello {profile?.livello_italiano ?? 'B1'}
        </Text>

        <View className="bg-[rgba(255,255,255,0.06)] p-6 rounded-[32px] mb-8 border border-[rgba(255,255,255,0.1)]">
          <Text className="text-xl font-bold text-white mb-4">Integrazioni API Private</Text>
          <TouchableOpacity
            onPress={connectGoogle}
            className="bg-[#DB4437] p-4 rounded-2xl items-center mb-2 flex-row justify-center shadow-lg"
          >
            <Text className="text-white font-bold text-lg">
              {busy === 'google' ? '⏳ Apertura...' : '📧 Connetti Gmail (OAuth)'}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={connectGoogle}
            className="bg-[#4285F4] p-4 rounded-2xl items-center flex-row justify-center shadow-lg"
          >
            <Text className="text-white font-bold text-lg">📅 Connetti Calendar</Text>
          </TouchableOpacity>
          <Text className="text-gray-400 text-sm mt-4 text-center px-4 leading-5">
            {google?.connesso
              ? `Collegato${google.email ? ` come ${google.email}` : ''}: ATLAS può leggere le email e gestire gli appuntamenti.`
              : google?.configurato
                ? 'Credenziali configurate: premi per autorizzare l\'account Google (una volta sola).'
                : 'Serve un client OAuth gratuito (GOOGLE_CLIENT_ID/SECRET nel .env). Tocca per le istruzioni.'}
          </Text>
        </View>

        <View className="bg-[rgba(255,255,255,0.06)] p-6 rounded-[32px] mb-8 border border-[rgba(255,255,255,0.1)]">
          <Text className="text-xl font-bold text-white mb-2">Notifiche</Text>
          <Text className="text-gray-400 mb-4">
            {devices} dispositivi collegati · {scheduled} promemoria locali pianificati
          </Text>
          <View className="flex-row justify-between items-center mb-4">
            <Text className="text-white text-lg font-bold">🔔 Notifiche attive</Text>
            <Switch
              value={notificationsOn}
              onValueChange={toggleNotifications}
              trackColor={{ false: '#333', true: '#7c3aed' }}
              thumbColor="#fff"
            />
          </View>
          <TouchableOpacity
            onPress={sendTest}
            disabled={busy === 'test'}
            className="bg-[#7c3aed] p-4 rounded-2xl items-center"
          >
            <Text className="text-white font-bold text-lg">
              {busy === 'test' ? 'Invio...' : 'Invia notifica di test'}
            </Text>
          </TouchableOpacity>
        </View>

        <View className="bg-[rgba(255,255,255,0.06)] p-6 rounded-[32px] mb-8 border border-[rgba(255,255,255,0.1)]">
          <View className="flex-row justify-between items-center mb-3">
            <Text className="text-xl font-bold text-white">⏰ Promemoria</Text>
            <Text className="text-gray-400 text-sm">{reminders.length}</Text>
          </View>
          <Text className="text-gray-400 mb-4">
            Creati dalla chat. La notifica locale funziona anche ad app chiusa; senza permesso resta il promemoria nella lista.
          </Text>
          {reminders.length ? (
            reminders.slice(0, 8).map((reminder) => (
              <View
                key={reminder.id}
                className="bg-[#ffffff08] p-4 rounded-2xl mb-3 border border-[#ffffff10]"
              >
                <View className="flex-row justify-between items-start">
                  <View className="flex-1 pr-3">
                    <Text className="text-white font-bold">{reminder.message}</Text>
                    <Text className="text-[#a5b4fc] text-sm mt-1">{formatReminderTime(reminder.remind_at)}</Text>
                    {reminder.include_todos && reminder.lista?.length ? (
                      <Text className="text-gray-400 text-xs mt-1" numberOfLines={2}>
                        🛒 {reminder.lista.join(', ')}
                      </Text>
                    ) : null}
                  </View>
                  <TouchableOpacity onPress={() => cancelReminder(reminder)} className="bg-[#ef444420] px-3 py-2 rounded-xl">
                    <Text className="text-[#fca5a5] font-bold text-sm">Annulla</Text>
                  </TouchableOpacity>
                </View>
              </View>
            ))
          ) : (
            <Text className="text-gray-400">Nessun promemoria attivo. Chiedi in chat: «Ricordami domani alle 9 di chiamare il medico».</Text>
          )}
        </View>

        <Text className="text-2xl font-bold text-white mb-5 ml-2">Regole Background (Cron)</Text>

        {row(
          '📅',
          'Smart Calendar',
          'ATLAS legge l\'agenda ogni ora e riassume gli appuntamenti.',
          automation('smart_calendar'),
          (next) => toggleAutomation('smart_calendar', next)
        )}

        {row(
          '☔',
          'Ombrello Smart',
          'Notifica se oggi pioverà (meteo reale ogni mattina).',
          automation('ombrello_smart'),
          (next) => toggleAutomation('ombrello_smart', next),
          '#06b6d4'
        )}

        {row(
          '💊',
          'Promemoria Pillola',
          'Avviso quotidiano salute famiglia.',
          automation('promemoria_pillola'),
          (next) => toggleAutomation('promemoria_pillola', next)
        )}

        {row(
          '📚',
          'Lezione Italiano',
          'Ogni mattina alle 7:30 la lezione del giorno.',
          automation('lezione_italiano'),
          (next) => toggleAutomation('lezione_italiano', next)
        )}

        {row(
          '💧',
          'Promemoria Acqua',
          'Un promemoria ogni due ore nelle ore diurne.',
          automation('promemoria_acqua'),
          (next) => toggleAutomation('promemoria_acqua', next),
          '#06b6d4'
        )}

        {row(
          '📈',
          'Price Watcher',
          'Avvisa se Bitcoin o Ethereum si muovono molto.',
          automation('price_watcher'),
          (next) => toggleAutomation('price_watcher', next)
        )}

        <Text className="text-2xl font-bold text-white mb-5 ml-2 mt-4">Sicurezza</Text>

        <TouchableOpacity
          onPress={() => navigation.navigate('CambioPin')}
          className="bg-[rgba(255,255,255,0.06)] p-5 rounded-3xl mb-8 border border-white/5 flex-row justify-between items-center"
        >
          <View className="flex-1 pr-4">
            <Text className="text-white text-xl font-bold">🔐 Cambia PIN</Text>
            <Text className="text-gray-400 mt-1">
              {isAdmin
                ? 'Aggiorna il PIN di un profilo: le sue sessioni aperte vengono chiuse subito.'
                : 'Solo l\'amministratore può cambiare i PIN della famiglia.'}
            </Text>
          </View>
          <Text className="text-[#a78bfa] font-bold text-2xl">›</Text>
        </TouchableOpacity>

        <Text className="text-2xl font-bold text-white mb-5 ml-2 mt-4">Gestione Profili</Text>

        <View className="bg-[rgba(255,255,255,0.06)] p-5 rounded-3xl mb-4 border border-white/5">
          {Object.entries(profiles).map(([slug, rowData]) => (
            <View key={slug} className="flex-row justify-between items-center py-2">
              <View className="flex-1 pr-3">
                <Text className="text-white font-bold">
                  {rowData.nome} {slug === profileId ? '· tu' : ''}
                </Text>
                <Text className="text-gray-400 text-sm">
                  {slug} · {rowData.livello_italiano}
                  {rowData.lingua_madre ? ` · ${rowData.lingua_madre}` : ''}
                </Text>
              </View>
              {isAdmin && slug !== profileId && slug !== 'io' ? (
                <TouchableOpacity
                  onPress={() => deleteProfile(slug, rowData.nome)}
                  className="bg-[#ef444420] px-3 py-2 rounded-xl"
                >
                  <Text className="text-[#fca5a5] font-bold text-sm">Elimina</Text>
                </TouchableOpacity>
              ) : null}
            </View>
          ))}

          {isAdmin ? (
            <>
          <TouchableOpacity
            onPress={() => setShowAddProfile((previous) => !previous)}
            className="bg-[#ffffff12] p-4 rounded-2xl items-center mt-3"
          >
            <Text className="text-white font-bold">{showAddProfile ? 'Chiudi' : '+ Aggiungi membro'}</Text>
          </TouchableOpacity>

          {showAddProfile ? (
            <View className="mt-4">
              <TextInput
                className="bg-[#ffffff10] text-white p-4 rounded-2xl mb-3"
                placeholder="Nome (es. Nonna)"
                placeholderTextColor="#888"
                value={newNome}
                onChangeText={setNewNome}
              />
              <TextInput
                className="bg-[#ffffff10] text-white p-4 rounded-2xl mb-3"
                placeholder="PIN di 4-8 cifre"
                placeholderTextColor="#888"
                keyboardType="number-pad"
                secureTextEntry
                maxLength={CONFIG.MAX_PIN_LENGTH}
                value={newPin}
                onChangeText={setNewPin}
              />
              <View className="flex-row flex-wrap mb-3">
                {LIVELLI.map((level) => (
                  <TouchableOpacity
                    key={level}
                    onPress={() => setNewLivello(level)}
                    className={`px-3 py-2 rounded-full mr-2 mb-2 ${
                      newLivello === level ? 'bg-[#7c3aed]' : 'bg-[#ffffff15]'
                    }`}
                  >
                    <Text className="text-white font-bold">{level}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <TouchableOpacity
                onPress={createProfile}
                disabled={busy === 'profilo'}
                className={`p-4 rounded-2xl items-center ${busy === 'profilo' ? 'bg-[#22c55e99]' : 'bg-[#22c55e]'}`}
              >
                <Text className="text-white font-black">
                  {busy === 'profilo' ? 'Creazione...' : 'Crea profilo'}
                </Text>
              </TouchableOpacity>
            </View>
          ) : null}
            </>
          ) : (
            <Text className="text-gray-400 text-sm mt-3 text-center">
              Solo l'amministratore può aggiungere o rimuovere membri della famiglia.
            </Text>
          )}
        </View>

        <TouchableOpacity
          onPress={logout}
          className="bg-[#ef444415] border border-[#ef444440] p-4 rounded-2xl items-center mb-10"
        >
          <Text className="text-[#fca5a5] font-bold text-lg">Esci dall'account</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}
