import React, { useCallback, useState } from 'react';
import { View, Text, ScrollView, SafeAreaView, TouchableOpacity, RefreshControl } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { useFocusEffect } from '@react-navigation/native';
import Animated, { FadeInUp } from 'react-native-reanimated';
import apiService, { DashboardData } from '../services/api';
import CONFIG from '../config';
import { useAuth } from '../../App';

interface HealthInfo {
  ok: boolean;
  versione?: string;
  profili?: number;
  ambiente?: string;
  db_mode?: string;
  automazioni?: number;
  llm?: boolean;
}

const EMPTY_DASHBOARD: DashboardData = {
  todos_totali: 0,
  todos_pendenti: 0,
  spesa_mese: 0,
  dispositivi_notifiche: 0,
  punti_italiano: 0,
  streak_italiano: 0,
};

export default function HomeScreen({ route, navigation }: any) {
  const { profileId: authProfileId } = useAuth();
  const profileId: string = route?.params?.profileId ?? authProfileId ?? 'io';

  const [refreshing, setRefreshing] = useState(false);
  const [health, setHealth] = useState<HealthInfo>({ ok: false });
  const [dashboard, setDashboard] = useState<DashboardData>(EMPTY_DASHBOARD);
  const [todoPreview, setTodoPreview] = useState<string>('');
  const [lastError, setLastError] = useState<string>('');

  const fetchData = useCallback(async () => {
    let healthOk = false;
    try {
      const result: any = await apiService.getHealth();
      healthOk = result?.status === 'ok';
      setHealth({
        ok: healthOk,
        versione: result?.versione,
        profili: result?.profili,
        ambiente: result?.ambiente,
        db_mode: result?.db_mode,
        automazioni: result?.automazioni,
        llm: result?.llm,
      });
      setLastError('');
    } catch (error: any) {
      setHealth({ ok: false });
      setLastError(error?.message ?? '');
    }

    if (!healthOk) {
      setDashboard(EMPTY_DASHBOARD);
      setTodoPreview('');
      return;
    }

    try {
      const dashboardResult = await apiService.getDashboard();
      setDashboard(dashboardResult.data ?? EMPTY_DASHBOARD);
    } catch {
      setDashboard(EMPTY_DASHBOARD);
    }

    try {
      const todosResult = await apiService.getTodos('pending');
      const tasks = (todosResult.data ?? [])
        .slice(0, 3)
        .map((todo) => todo.task)
        .filter(Boolean) as string[];
      setTodoPreview(tasks.length ? tasks.join(', ') : '');
    } catch {
      setTodoPreview('');
    }
  }, []);

  // Aggiorna i numeri al primo accesso e quando si torna sulla tab Home.
  useFocusEffect(
    useCallback(() => {
      fetchData();
    }, [fetchData])
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await fetchData();
    setRefreshing(false);
  };

  const stato = health.ok ? '🟢 Sistema online' : '🔴 Backend non collegato';
  const automazioni = health.automazioni ?? 0;

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
            {stato} · {CONFIG.API_URL}
          </Text>
        </Animated.View>

        <Animated.View entering={FadeInUp.delay(100)} className="bg-gradient-to-r from-[#1e1b4b] to-[#0f0f2d] p-6 rounded-[32px] mb-4 border border-[#7c3aed30]">
          <Text className="text-white/60 text-xs uppercase font-bold tracking-widest">Stato Sistema</Text>
          <Text className="text-white text-2xl font-bold mt-2">
            {health.ok ? `✅ Backend connesso · ${health.profili ?? 0} profili` : 'ℹ️ Backend non raggiungibile'}
          </Text>
          <Text className="text-[#a5b4fc] mt-1">
            {health.ok
              ? `Automazioni: ${automazioni} attive`
              : 'Avvia il backend Python sulla stessa rete'}
          </Text>
        </Animated.View>

        <Animated.View entering={FadeInUp.delay(200)} className="bg-[#1c1917] p-6 rounded-[32px] mb-4 border border-[#f59e0b30]">
          <Text className="text-white/60 text-xs uppercase font-bold tracking-widest">Versione Build</Text>
          <Text className="text-white text-2xl font-bold mt-2">
            {health.ok
              ? `v${health.versione ?? '3.0.0'} · ${health.ambiente ?? 'development'}`
              : 'Sistema offline'}
          </Text>
          <View className="flex-row mt-3 flex-wrap">
            <View className={`px-3 py-1 rounded-full mr-2 ${health.ok ? 'bg-[#22c55e20]' : 'bg-[#ef444420]'}`}>
              <Text className={`text-sm font-bold ${health.ok ? 'text-[#22c55e]' : 'text-[#ef4444]'}`}>
                {health.ok ? '📈 Connesso' : '📉 Offline'}
              </Text>
            </View>
            <View className="px-3 py-1 rounded-full bg-[#ffffff12]">
              <Text className="text-[#e5e7eb] text-sm font-bold">
                DB: {health.db_mode === 'supabase' ? 'Supabase' : 'locale'}
              </Text>
            </View>
          </View>
          {!health.ok && lastError ? (
            <Text className="text-[#fca5a5] text-xs mt-3">{lastError}</Text>
          ) : null}
        </Animated.View>

        <Animated.View entering={FadeInUp.delay(300)} className="bg-[#1b1b2e] p-6 rounded-[32px] mb-4 border border-[#06b6d430]">
          <Text className="text-white/60 text-xs uppercase font-bold tracking-widest">In Arrivo</Text>
          <Text className="text-white text-2xl font-bold mt-2">
            📧 {dashboard.dispositivi_notifiche} dispositivi collegati
          </Text>
          <Text className="text-[#67e8f9] mt-1">
            {health.ok
              ? 'Notifiche push per nuove automazioni'
              : 'Collega il backend per ricevere le notifiche'}
          </Text>
        </Animated.View>

        <Animated.View entering={FadeInUp.delay(400)} className="bg-[#2d1b1b] p-6 rounded-[32px] mb-4 border border-[#ef444430]">
          <Text className="text-white/60 text-xs uppercase font-bold tracking-widest">Lista Attività</Text>
          <Text className="text-white text-lg font-bold mt-2">
            🛒 {todoPreview || 'Nessun task attivo'}
          </Text>
          <Text className="text-[#fca5a5] mt-1">
            {dashboard.todos_pendenti} da fare · €{dashboard.spesa_mese.toFixed(2)} spesi questo mese
          </Text>
          <Text className="text-[#fca5a5] mt-1">Vai alla Chat per aggiungere task</Text>
        </Animated.View>

        <Text className="text-white font-bold text-xl mb-4 mt-2">Azioni Rapide</Text>
        <View className="flex-row flex-wrap justify-between">
          {[
            { icon: '💰', title: 'Budget', screen: 'Budget', color: 'border-[#22c55e40]' },
            { icon: '🇮🇹', title: 'Italiano', screen: 'Italiano', color: 'border-[#7c3aed40]' },
            { icon: '💬', title: 'Chat AI', screen: 'Chat', color: 'border-[#06b6d440]' },
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
