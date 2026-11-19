import React, { useState } from 'react';
import {
  ActivityIndicator,
  SafeAreaView,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import apiService, { ApiError } from '../services/api';
import CONFIG from '../config';
import { useAuth } from '../../App';

/**
 * Schermata di blocco automatico.
 *
 * Compare quando l'app resta inattiva o torna dal background dopo
 * `CONFIG.AUTO_LOCK_MINUTES`: il token salvato non basta più, serve il PIN.
 * Un PIN corretto emette un token nuovo (e azzera il contatore degli errori);
 * "Esci" chiude la sessione su questo dispositivo.
 */
export default function LockScreen({ onUnlock }: { onUnlock: () => void }) {
  const { profileId, profile, setAuth, clearAuth } = useAuth();
  const [pin, setPin] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const sblocca = async () => {
    if (!profileId || busy || pin.length < CONFIG.MIN_PIN_LENGTH) return;
    setBusy(true);
    setError('');
    try {
      const result = await apiService.verifyPin(profileId, pin);
      if (result.auth && result.token) {
        await setAuth(result.token, result.slug || profileId);
        setPin('');
        onUnlock();
      } else {
        setPin('');
        setError(result.message || 'PIN errato. Riprova.');
      }
    } catch (err: any) {
      setPin('');
      if (err instanceof ApiError && err.status === 429) {
        setError(err.message || 'Troppi tentativi: riprova tra qualche minuto.');
      } else if (err instanceof ApiError && err.status === 422) {
        setError('PIN non valido: usa solo cifre (4-8).');
      } else {
        setError(err?.message || 'Impossibile verificare il PIN. Controlla la rete.');
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <SafeAreaView className="flex-1 bg-[#0a0a0f] justify-center items-center px-6">
      <StatusBar style="light" />
      <Text className="text-5xl mb-4">🔒</Text>
      <Text className="text-2xl font-black text-white text-center">App bloccata</Text>
      <Text className="text-gray-400 text-center mt-2 mb-8">
        {profile?.nome ? `Ciao ${profile.nome}, ` : ''}inserisci il PIN per riprendere.
      </Text>

      <View
        className="bg-[#ffffff08] p-6 rounded-[32px] w-full border border-white/10"
        style={{ maxWidth: 340 }}
      >
        <TextInput
          className="bg-[#ffffff15] text-white text-3xl text-center p-4 rounded-2xl mb-3 tracking-[10px]"
          placeholder="••••"
          placeholderTextColor="#888"
          secureTextEntry
          keyboardType="number-pad"
          maxLength={CONFIG.MAX_PIN_LENGTH}
          value={pin}
          onChangeText={(value) => {
            setPin(value);
            if (error) setError('');
          }}
          onSubmitEditing={sblocca}
        />
        {error ? <Text className="text-[#fca5a5] text-center mb-3">{error}</Text> : null}

        <TouchableOpacity
          onPress={sblocca}
          disabled={busy || pin.length < CONFIG.MIN_PIN_LENGTH}
          className={`p-4 rounded-2xl items-center ${
            busy || pin.length < CONFIG.MIN_PIN_LENGTH ? 'bg-[#7c3aed80]' : 'bg-[#7c3aed]'
          }`}
        >
          {busy ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text className="text-white font-black text-lg">Sblocca</Text>
          )}
        </TouchableOpacity>

        <TouchableOpacity onPress={() => clearAuth()} className="mt-4 items-center">
          <Text className="text-[#8888a0]">Esci da questo dispositivo</Text>
        </TouchableOpacity>
      </View>

      <Text className="text-gray-600 text-xs text-center mt-6 px-6 leading-5">
        Il blocco scatta dopo {CONFIG.AUTO_LOCK_MINUTES} minuti di inattività o quando torni
        all'app dopo una pausa. Se hai dimenticato il PIN, chiudi la sessione e usa il codice
        di recupero dalla schermata dei profili.
      </Text>
    </SafeAreaView>
  );
}
