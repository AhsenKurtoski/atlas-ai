import React, { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, SafeAreaView, ScrollView, TextInput, Alert } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import Animated, { FadeInUp } from 'react-native-reanimated';
import apiService, { ApiError, ProfileRow } from '../services/api';
import CONFIG from '../config';
import { useAuth } from '../../App';

interface ProfileCard {
  id: string;
  nome: string;
  icona: string;
  livello: string;
  colore: string;
}

const FALLBACK_PROFILES: ProfileCard[] = [
  { id: 'io', nome: 'Tu (Admin)', icona: '👦', livello: 'C1', colore: '#7c3aed' },
  { id: 'mamma', nome: 'Mamma', icona: '👩', livello: 'B1', colore: '#ec4899' },
  { id: 'papa', nome: 'Papà', icona: '👨', livello: 'A2', colore: '#3b82f6' },
  { id: 'fratello1', nome: 'Fratello 1', icona: '🧑', livello: 'Madrelingua', colore: '#f59e0b' },
  { id: 'fratello2', nome: 'Fratello 2', icona: '👨‍🦱', livello: 'Madrelingua', colore: '#10b981' },
];

const COLORS = ['#7c3aed', '#ec4899', '#3b82f6', '#f59e0b', '#10b981', '#06b6d4'];
const ICONS = ['👦', '👩', '👨', '🧑', '👨‍🦱', '👧', '👵', '👴'];

function toCard(slug: string, row: ProfileRow, index: number): ProfileCard {
  return {
    id: slug,
    nome: row.nome || slug,
    icona: ICONS[index % ICONS.length],
    livello: row.livello_italiano || 'B1',
    colore: COLORS[index % COLORS.length],
  };
}

export default function ProfileScreen() {
  const { setAuth } = useAuth();
  const [profiles, setProfiles] = useState<ProfileCard[]>(FALLBACK_PROFILES);
  const [showPin, setShowPin] = useState(false);
  const [selectedProfile, setSelectedProfile] = useState('');
  const [pin, setPin] = useState('');
  const [verifying, setVerifying] = useState(false);

  // I profili vengono dal backend: nomi e livelli reali (modificabili in Impostazioni).
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const data = await apiService.getProfiles();
        const entries = Object.entries(data || {});
        if (active && entries.length) {
          setProfiles(entries.map(([slug, row], index) => toCard(slug, row, index)));
        }
      } catch {
        // Backend offline: restano i profili predefiniti.
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const selectProfile = (profile: ProfileCard) => {
    setSelectedProfile(profile.id);
    setShowPin(true);
    setPin('');
  };

  const verifyPin = async () => {
    if (!pin || verifying) return;
    if (pin.length < CONFIG.MIN_PIN_LENGTH) {
      Alert.alert('PIN troppo corto', `Il PIN ha almeno ${CONFIG.MIN_PIN_LENGTH} cifre.`);
      return;
    }
    setVerifying(true);
    try {
      const result = await apiService.verifyPin(selectedProfile, pin);
      if (result.auth && result.token) {
        // Il cambio di stato nel context fa comparire la navigazione principale.
        await setAuth(result.token, result.slug || selectedProfile);
        setShowPin(false);
        setPin('');
      } else {
        Alert.alert('Accesso negato', result.message || 'PIN errato. Riprova.');
        setPin('');
      }
    } catch (error: any) {
      let message = error?.message || 'Errore di connessione al backend.';
      if (error instanceof ApiError && error.status === 429) {
        message = 'Troppi tentativi. Riprova tra un minuto.';
      } else if (error instanceof ApiError && error.status === 422) {
        message = 'PIN non valido: usa solo cifre (4-8).';
      }
      Alert.alert('Errore', message);
      setPin('');
    } finally {
      setVerifying(false);
    }
  };

  if (showPin) {
    const profile = profiles.find((item) => item.id === selectedProfile);
    return (
      <SafeAreaView className="flex-1 bg-[#0a0a0f] justify-center items-center">
        <StatusBar style="light" />
        <Text className="text-3xl font-black text-white mb-6">Inserisci PIN</Text>
        <View className="bg-[#ffffff08] p-8 rounded-[32px] items-center w-[300]">
          <Text className="text-6xl mb-4">{profile?.icona}</Text>
          <Text className="text-white text-xl font-bold mb-6">{profile?.nome}</Text>
          <TextInput
            className="bg-[#ffffff15] text-white text-4xl text-center p-4 rounded-2xl w-full mb-6 tracking-[10px]"
            placeholder="****"
            placeholderTextColor="#888"
            secureTextEntry
            maxLength={CONFIG.MAX_PIN_LENGTH}
            keyboardType="number-pad"
            value={pin}
            onChangeText={setPin}
          />
          <TouchableOpacity
            onPress={verifyPin}
            disabled={verifying || pin.length < CONFIG.MIN_PIN_LENGTH}
            className={`py-4 px-12 rounded-2xl w-full items-center ${
              verifying || pin.length < CONFIG.MIN_PIN_LENGTH ? 'bg-[#7c3aed80]' : 'bg-[#7c3aed]'
            }`}
          >
            <Text className="text-white font-black text-lg">
              {verifying ? 'Verifica...' : 'Sblocca 🔓'}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={() => {
              setShowPin(false);
              setPin('');
            }}
            className="mt-4"
          >
            <Text className="text-[#8888a0]">← Cambia profilo</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView className="flex-1 bg-[#0a0a0f]">
      <StatusBar style="light" />
      <ScrollView contentContainerStyle={{ padding: 20, paddingTop: 60, alignItems: 'center' }}>
        <Animated.View entering={FadeInUp}>
          <Text className="text-4xl font-black text-white mb-2">🧠 ATLAS AI</Text>
          <Text className="text-[#8888a0] text-lg mb-10 text-center">Chi sei oggi?</Text>
        </Animated.View>

        <View className="flex-row flex-wrap justify-between w-full">
          {profiles.map((profile, i) => (
            <Animated.View key={profile.id} entering={FadeInUp.delay(i * 80)} className="w-[48%] mb-4">
              <TouchableOpacity
                onPress={() => selectProfile(profile)}
                className="p-6 rounded-[32px] items-center border"
                style={{ backgroundColor: `${profile.colore}15`, borderColor: `${profile.colore}40` }}
              >
                <Text className="text-6xl mb-3">{profile.icona}</Text>
                <Text className="text-white text-xl font-bold text-center">{profile.nome}</Text>
                {profile.livello ? (
                  <View className="bg-[#ffffff15] px-3 py-1 rounded-full mt-2">
                    <Text className="text-white text-sm">Livello {profile.livello}</Text>
                  </View>
                ) : null}
              </TouchableOpacity>
            </Animated.View>
          ))}

          <Animated.View entering={FadeInUp.delay(profiles.length * 80)} className="w-[48%] mb-4">
            <TouchableOpacity
              onPress={() =>
                Alert.alert(
                  'Aggiungi un profilo',
                  'Accedi con il tuo profilo e vai in Impostazioni → Gestione Profili per creare un nuovo membro della famiglia.'
                )
              }
              className="p-6 rounded-[32px] items-center border"
              style={{ backgroundColor: '#ffffff0a', borderColor: '#ffffff30' }}
            >
              <Text className="text-6xl mb-3 text-white">+</Text>
              <Text className="text-white text-xl font-bold text-center">Aggiungi Profilo</Text>
            </TouchableOpacity>
          </Animated.View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
