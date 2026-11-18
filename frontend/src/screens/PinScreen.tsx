import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  SafeAreaView,
  ScrollView,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { useFocusEffect } from '@react-navigation/native';
import apiService, { ApiError, ProfileRow } from '../services/api';
import CONFIG from '../config';
import { useAuth } from '../../App';

/**
 * Cambio PIN dall'app (Impostazioni → Cambia PIN).
 *
 * Usa `POST /profili/{slug}/pin`, riservato all'amministratore `io`: il backend
 * salva solo l'hash bcrypt e chiude le sessioni già aperte di quel profilo.
 * Se l'amministratore cambia il proprio PIN, anche questa sessione decade e
 * l'app torna alla schermata dei profili.
 */
export default function PinScreen({ route }: any) {
  const { profileId, clearAuth } = useAuth();
  const isAdmin = profileId === 'io';

  const [profiles, setProfiles] = useState<Record<string, ProfileRow>>({});
  const [selected, setSelected] = useState<string>(route?.params?.slug ?? profileId ?? '');
  const [pin, setPin] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await apiService.getProfiles();
      setProfiles(data ?? {});
    } catch (error: any) {
      Alert.alert('Errore', error?.message ?? 'Impossibile leggere i profili.');
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  useEffect(() => {
    if (!selected && profileId) setSelected(profileId);
  }, [profileId, selected]);

  const salva = async () => {
    if (busy) return;
    if (!selected) {
      Alert.alert('Scegli un profilo', 'Seleziona il profilo di cui vuoi cambiare il PIN.');
      return;
    }
    if (pin.length < CONFIG.MIN_PIN_LENGTH || pin.length > CONFIG.MAX_PIN_LENGTH) {
      Alert.alert('PIN non valido', `Il PIN deve avere da ${CONFIG.MIN_PIN_LENGTH} a ${CONFIG.MAX_PIN_LENGTH} cifre.`);
      return;
    }
    if (!/^\d+$/.test(pin)) {
      Alert.alert('PIN non valido', 'Usa solo cifre.');
      return;
    }
    if (pin !== confirm) {
      Alert.alert('PIN diversi', 'I due PIN inseriti non coincidono.');
      return;
    }

    setBusy(true);
    try {
      const result = await apiService.changePin(selected, pin);
      if (result.status !== 'ok') {
        Alert.alert('PIN non cambiato', result.message ?? 'Errore sconosciuto.');
        return;
      }
      setPin('');
      setConfirm('');

      if (selected === profileId) {
        // Il PIN appena cambiato è il nostro: la sessione corrente è stata revocata.
        Alert.alert(
          'PIN aggiornato',
          'Le sessioni aperte con il vecchio PIN sono state chiuse, compresa questa. Accedi di nuovo con il nuovo PIN.',
          [{ text: 'Accedi', onPress: () => clearAuth() }]
        );
      } else {
        Alert.alert('PIN aggiornato', result.message ?? 'Il profilo dovrà accedere con il nuovo PIN.');
      }
    } catch (error: any) {
      let message = error?.message ?? 'Cambio PIN non riuscito.';
      if (error instanceof ApiError && error.status === 403) {
        message = 'Solo l\'amministratore può cambiare i PIN.';
      } else if (error instanceof ApiError && error.status === 401) {
        message = 'Sessione non valida: accedi di nuovo.';
      } else if (error instanceof ApiError && error.status === 422) {
        message = 'PIN non valido: usa da 4 a 8 cifre.';
      } else if (error instanceof ApiError && error.status === 429) {
        message = 'Troppi tentativi ravvicinati: riprova tra un minuto.';
      }
      Alert.alert('Errore', message);
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <SafeAreaView className="flex-1 bg-[#0a0a0f] items-center justify-center">
        <StatusBar style="light" />
        <ActivityIndicator color="#7c3aed" size="large" />
      </SafeAreaView>
    );
  }

  const profiloSelezionato = profiles[selected];

  return (
    <SafeAreaView className="flex-1 bg-[#0a0a0f]">
      <StatusBar style="light" />
      <ScrollView className="flex-1 p-5" keyboardShouldPersistTaps="handled">
        <Text className="text-3xl font-black text-white mt-4 mb-2">🔐 Cambia PIN</Text>
        <Text className="text-gray-400 mb-6">
          Il nuovo PIN sostituisce subito il precedente e chiude le sessioni già aperte di quel profilo.
        </Text>

        {!isAdmin ? (
          <View className="bg-[rgba(255,255,255,0.06)] p-6 rounded-[32px] border border-white/10">
            <Text className="text-white text-lg font-bold mb-2">Solo per l'amministratore</Text>
            <Text className="text-gray-400 leading-6">
              I PIN della famiglia può cambiarli solo il profilo amministratore (<Text className="text-white font-bold">io</Text>).
              Accedi con quel profilo per gestirli.
            </Text>
          </View>
        ) : (
          <>
            <View className="bg-[rgba(255,255,255,0.06)] p-6 rounded-[32px] mb-6 border border-white/10">
              <Text className="text-white text-lg font-bold mb-4">Profilo</Text>
              <View className="flex-row flex-wrap">
                {Object.entries(profiles).map(([slug, rowData]) => (
                  <TouchableOpacity
                    key={slug}
                    onPress={() => setSelected(slug)}
                    className={`px-4 py-3 rounded-2xl mr-2 mb-2 border ${
                      selected === slug ? 'bg-[#7c3aed] border-[#7c3aed]' : 'bg-[#ffffff10] border-white/10'
                    }`}
                  >
                    <Text className="text-white font-bold">
                      {rowData.nome}
                      {slug === profileId ? ' · tu' : ''}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
              {profiloSelezionato ? (
                <Text className="text-gray-400 text-sm mt-2">
                  {profiloSelezionato.nome} · livello {profiloSelezionato.livello_italiano}
                  {profiloSelezionato.lingua_madre ? ` · ${profiloSelezionato.lingua_madre}` : ''}
                </Text>
              ) : null}
            </View>

            <View className="bg-[rgba(255,255,255,0.06)] p-6 rounded-[32px] mb-6 border border-white/10">
              <Text className="text-white text-lg font-bold mb-4">Nuovo PIN</Text>
              <TextInput
                className="bg-[#ffffff10] text-white text-2xl text-center p-4 rounded-2xl mb-3 tracking-[8px]"
                placeholder="••••"
                placeholderTextColor="#666"
                keyboardType="number-pad"
                secureTextEntry
                maxLength={CONFIG.MAX_PIN_LENGTH}
                value={pin}
                onChangeText={setPin}
              />
              <TextInput
                className="bg-[#ffffff10] text-white text-2xl text-center p-4 rounded-2xl tracking-[8px]"
                placeholder="Ripeti il PIN"
                placeholderTextColor="#666"
                keyboardType="number-pad"
                secureTextEntry
                maxLength={CONFIG.MAX_PIN_LENGTH}
                value={confirm}
                onChangeText={setConfirm}
              />
              <Text className="text-gray-500 text-sm mt-3">
                Da {CONFIG.MIN_PIN_LENGTH} a {CONFIG.MAX_PIN_LENGTH} cifre. PIN demo (0000, 1111, …) rifiutati in produzione.
              </Text>

              <TouchableOpacity
                onPress={salva}
                disabled={busy || !selected || pin.length < CONFIG.MIN_PIN_LENGTH}
                className={`mt-5 p-4 rounded-2xl items-center ${
                  busy || !selected || pin.length < CONFIG.MIN_PIN_LENGTH
                    ? 'bg-[#7c3aed80]'
                    : 'bg-[#7c3aed]'
                }`}
              >
                <Text className="text-white font-black text-lg">
                  {busy ? 'Salvataggio...' : 'Aggiorna PIN'}
                </Text>
              </TouchableOpacity>
            </View>

            <Text className="text-gray-500 text-sm mb-10 leading-5">
              Dopo il cambio, il profilo deve accedere di nuovo con il nuovo PIN; il vecchio PIN smette di funzionare
              immediatamente. Se cambi il PIN di <Text className="text-gray-300 font-bold">io</Text>, anche questa sessione
              viene chiusa.
            </Text>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}
