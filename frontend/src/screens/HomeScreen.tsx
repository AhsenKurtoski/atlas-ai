import React, { useState, useEffect } from 'react';
import { View, Text, ScrollView, SafeAreaView, TouchableOpacity, RefreshControl } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import Animated, { FadeInUp } from 'react-native-reanimated';
import apiService from '../services/api';
import CONFIG from '../config';

export default function HomeScreen({ route, navigation }: any) {
  const { profileId } = route.params;
  const [refreshing, setRefreshing] = useState(false);
  const [meteo, setMeteo] = useState('Caricamento...');
  const [crypto, setCrypto] = useState('Caricamento...');
  const [emailCount, setEmailCount] = useState<number | null>(null);
  const [todoPreview, setTodoPreview] = useState<string>('');
  const [serverStatus, setServerStatus] = useState<{ ok: boolean; versione?: string; profili?: number }>({ ok: false });

  const fetchData = async () => {
    try {
      const base = CONFIG.API_URL;
      let health: any = null;
      try {
        health = await (await fetch(base, { method: 'GET' })).json();
        setServerStatus({
          ok: health?.status === 'ok',
          versione: health?.versione,
          profili: health?.profili,
        });
      } catch {
        setServerStatus({ ok: false });
      }

      let todos: any[] = [];
      try {
        const tr = await apiService.getTodos('pending');
        todos = (tr?.data as any[]) || [];
      } catch {
        todos = [];
      }

      const tasks = todos.slice(0, 3).map((t: any) => t.task).filter(Boolean);
      setTodoPreview(tasks.length ? tasks.join(', ') : 'Nessun task attivo');
      setEmailCount(todos.length + 2);

      if (health?.status === 'ok') {
        setMeteo(`✅ Backend connesso · ${health.profili || 0} profili`);
        setCrypto(health.versione ? `v${health.versione} · ambiente ${health.ambiente || 'dev'}` : 'Sistema attivo');
      } else {
        setMeteo('ℹ️ Backend non raggiungibile');
        setCrypto('ℹ️ Avvia il backend Python');
      }
    } catch (e: any) {
      setMeteo('ℹ️ Collega il backend');
      setCrypto('ℹ️ Backend offline');
    }
  };

  useEffect(() => { fetchData(); }, []);

  const onRefresh = async () => {
    setRefreshing(true);
    await fetchData();
    setRefreshing(false);
  };

  return (
    <SafeAreaView className="flex-1 bg-[#0a0a0f]">
      <StatusBar style="light" />
      <ScrollView
        className="flex-1 p-4"
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#7c3aed" />}
      >
        <Animated.View entering={FadeInUp} className="mb-6">
          <Text className="text-[#8888a0] text-sm font-bold uppercase tracking-widest">Benvenuto</Text>
          <Text className="text-3xl font-black text-white mt-1">🧠 ATLAS AI</Text>
          <Text className="text-[#7c3aed] text-lg font-bold mt-1">{(profileId || '').toUpperCase()}</Text>
          <Text className="text-[#8888a0] text-xs mt-2">
            {serverStatus.ok ? '🟢 Sistema online' : '🔴 Backend non collegato'} · {CONFIG.API_URL}
          </Text>
        </Animated.View>

        <Animated.View entering={FadeInUp.delay(100)} className="bg-gradient-to-r from-[#1e1b4b] to-[#0f0f2d] p-6 rounded-[32px] mb-4 border border-[#7c3aed30]">
          <Text className="text-white/60 text-xs uppercase font-bold tracking-widest">Stato Sistema</Text>
          <Text className="text-white text-2xl font-bold mt-2">{meteo}</Text>
          <Text className="text-[#a5b4fc] mt-1">{serverStatus.ok ? 'Automazioni: 8 attive' : 'Backend in modalità offline'}</Text>
        </Animated.View>

        <Animated.View entering={FadeInUp.delay(200)} className="bg-[#1c1917] p-6 rounded-[32px] mb-4 border border-[#f59e0b30]">
          <Text className="text-white/60 text-xs uppercase font-bold tracking-widest">Versione Build</Text>
          <Text className="text-white text-2xl font-bold mt-2">{crypto}</Text>
          <View className="flex-row mt-3">
            <View className={`px-3 py-1 rounded-full mr-2 ${serverStatus.ok ? 'bg-[#22c55e20]' : 'bg-[#ef444420]'}`}>
              <Text className={`text-sm font-bold ${serverStatus.ok ? 'text-[#22c55e]' : 'text-[#ef4444]'}`}>
                {serverStatus.ok ? '📈 Connesso' : '📉 Offline'}
              </Text>
            </View>
            <Text className="text-gray-400 text-sm self-center">Stato backend</Text>
          </View>
        </Animated.View>

        <Animated.View entering={FadeInUp.delay(300)} className="bg-[#1b1b2e] p-6 rounded-[32px] mb-4 border border-[#06b6d430]">
          <Text className="text-white/60 text-xs uppercase font-bold tracking-widest">In Arrivo</Text>
          <Text className="text-white text-2xl font-bold mt-2">
            📧 {emailCount != null ? `${emailCount} aggiornamenti` : 'Controllo in corso...'}
          </Text>
          <Text className="text-[#67e8f9] mt-1">Notifiche push per nuove automazioni</Text>
        </Animated.View>

        <Animated.View entering={FadeInUp.delay(400)} className="bg-[#2d1b1b] p-6 rounded-[32px] mb-4 border border-[#ef444430]">
          <Text className="text-white/60 text-xs uppercase font-bold tracking-widest">Lista Attività</Text>
          <Text className="text-white text-lg font-bold mt-2">🛒 {todoPreview || 'Nessun task'}</Text>
          <Text className="text-[#fca5a5] mt-1">Vai alla Chat per aggiungere task</Text>
        </Animated.View>

        <Text className="text-white font-bold text-xl mb-4 mt-2">Azioni Rapide</Text>
        <View className="flex-row flex-wrap justify-between">
          {[
            { icon: '💰', title: 'Budget', screen: 'Budget', color: 'border-[#22c55e40]' },
            { icon: '🇮🇹', title: 'Italiano', screen: 'Italiano', color: 'border-[#7c3aed40]' },
            { icon: '�', title: 'Chat AI', screen: 'Chat', color: 'border-[#06b6d440]' },
            { icon: '⚙️', title: 'Impostazioni', screen: 'Impostazioni', color: 'border-[#f59e0b40]' },
          ].map((item, i) => (
            <TouchableOpacity
              key={i}
              onPress={() => navigation.navigate(item.screen)}
              className={`bg-[#ffffff08] w-[48%] p-5 rounded-2xl items-center mb-3 border ${item.color}`}
            >
              <Text className="text-3xl mb-2">{item.icon}</Text>
              <Text className="text-white font-bold">{item.title}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <View className="h-10" />
      </ScrollView>
    </SafeAreaView>
  );
}
