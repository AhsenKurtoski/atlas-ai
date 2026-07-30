import React, { useState } from 'react';
import { View, Text, TouchableOpacity, SafeAreaView, ScrollView, TextInput, Alert } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import Animated, { FadeInUp } from 'react-native-reanimated';
import AsyncStorage from '@react-native-async-storage/async-storage';
import apiService from '../services/api';
import CONFIG from '../config';
import { useAuth } from '../../App';

const PROFILES = [
  { id: 'io', nome: 'Tu (Admin)', icona: '👦', livello: 'C1', colore: '#7c3aed' },
  { id: 'mamma', nome: 'Mamma', icona: '👩', livello: 'B1', colore: '#ec4899' },
  { id: 'papa', nome: 'Papà', icona: '👨', livello: 'A2', colore: '#3b82f6' },
  { id: 'fratello1', nome: 'Fratello 1', icona: '🧑', livello: 'B2', colore: '#f59e0b' },
  { id: 'fratello2', nome: 'Fratello 2', icona: '👨‍🦱', livello: 'C1', colore: '#10b981' },
  { id: 'aggiungi', nome: 'Aggiungi Profilo', icona: '+', livello: '', colore: '#ffffff30' },
];

export default function ProfileScreen({ navigation }: any) {
  const { setAuth } = useAuth();
  const [showPin, setShowPin] = useState(false);
  const [selectedProfile, setSelectedProfile] = useState('');
  const [pin, setPin] = useState('');
  const [verifying, setVerifying] = useState(false);

  const selectProfile = (profile: any) => {
    if (profile.id === 'aggiungi') {
      Alert.alert('Info', 'Vai su Impostazioni > Gestione Profili per aggiungere un nuovo membro della famiglia.');
      return;
    }
    setSelectedProfile(profile.id);
    setShowPin(true);
    setPin('');
  };

  const verifyPin = async () => {
    if (!pin || verifying) return;
    setVerifying(true);
    try {
      const res = await apiService.verifyPin(selectedProfile, pin);
      if (res.auth && res.token) {
        await setAuth(res.token, selectedProfile);
        setShowPin(false);
        setPin('');
        navigation.navigate('Main', { profileId: selectedProfile, authToken: res.token });
      } else {
        Alert.alert('Accesso negato', res.message || 'PIN errato. Riprova.');
        setPin('');
      }
    } catch (e: any) {
      const msg = /rate|limit|troppi/i.test(e?.message || '')
        ? 'Troppi tentativi. Riprova tra un minuto.'
        : (e?.message || 'Errore di connessione al backend.');
      Alert.alert('Errore', msg);
      setPin('');
    } finally {
      setVerifying(false);
    }
  };

  if (showPin) {
    const prof = PROFILES.find(p => p.id === selectedProfile);
    return (
      <SafeAreaView className="flex-1 bg-[#0a0a0f] justify-center items-center">
        <StatusBar style="light" />
        <Text className="text-3xl font-black text-white mb-6">Inserisci PIN</Text>
        <View className="bg-[#ffffff08] p-8 rounded-[32px] items-center w-[300]">
          <Text className="text-6xl mb-4">{prof?.icona}</Text>
          <Text className="text-white text-xl font-bold mb-6">{prof?.nome}</Text>
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
            disabled={verifying || pin.length < 4}
            className={`py-4 px-12 rounded-2xl w-full items-center ${verifying || pin.length < 4 ? 'bg-[#7c3aed80]' : 'bg-[#7c3aed]'}`}
          >
            <Text className="text-white font-black text-lg">
              {verifying ? 'Verifica...' : 'Sblocca 🔓'}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => { setShowPin(false); setPin(''); }} className="mt-4">
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
          {PROFILES.map((prof, i) => (
            <Animated.View key={prof.id} entering={FadeInUp.delay(i * 80)} className="w-[48%] mb-4">
              <TouchableOpacity
                onPress={() => selectProfile(prof)}
                className={`p-6 rounded-[32px] items-center border`}
                style={{ backgroundColor: `${prof.colore}15`, borderColor: `${prof.colore}40` }}
              >
                <Text className="text-6xl mb-3">{prof.icona}</Text>
                <Text className="text-white text-xl font-bold text-center">{prof.nome}</Text>
                {prof.livello ? (
                  <View className="bg-[#ffffff15] px-3 py-1 rounded-full mt-2">
                    <Text className="text-white text-sm">Livello {prof.livello}</Text>
                  </View>
                ) : null}
              </TouchableOpacity>
            </Animated.View>
          ))}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
