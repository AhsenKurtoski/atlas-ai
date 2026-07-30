import React from 'react';
import { View, Text, Switch, TouchableOpacity, ScrollView, SafeAreaView } from 'react-native';
import { StatusBar } from 'expo-status-bar';

export default function IntegrationsScreen() {
  const [calendarEnabled, setCalendarEnabled] = React.useState(true);
  const [umbrellaEnabled, setUmbrellaEnabled] = React.useState(true);
  const [pillsEnabled, setPillsEnabled] = React.useState(false);
  
  return (
    <SafeAreaView className="flex-1 bg-[#0a0a0f]">
      <StatusBar style="light" />
      <ScrollView className="flex-1 p-5">
        <Text className="text-4xl font-extrabold text-white mb-8 mt-4">Hub Automazioni</Text>

        <View className="bg-[rgba(255,255,255,0.06)] p-6 rounded-[32px] mb-8 border border-[rgba(255,255,255,0.1)]">
          <Text className="text-xl font-bold text-white mb-4">Integrazioni API Private</Text>
          <TouchableOpacity className="bg-[#DB4437] p-4 rounded-2xl items-center mb-4 flex-row justify-center shadow-lg">
            <Text className="text-white font-bold text-lg">📧 Connetti Gmail (OAuth)</Text>
          </TouchableOpacity>
          <TouchableOpacity className="bg-[#4285F4] p-4 rounded-2xl items-center flex-row justify-center shadow-lg">
            <Text className="text-white font-bold text-lg">📅 Connetti Calendar</Text>
          </TouchableOpacity>
          <Text className="text-gray-400 text-sm mt-5 text-center px-4 leading-5">
            Necessario per far leggere le email ad ATLAS e salvare gli appuntamenti (es. Visita Medica) sul calendario.
          </Text>
        </View>

        <Text className="text-2xl font-bold text-white mb-5 ml-2">Regole Background (Cron)</Text>

        <View className="bg-[rgba(255,255,255,0.06)] p-5 rounded-3xl mb-4 flex-row justify-between items-center border border-white/5">
          <View className="flex-1 pr-4">
            <Text className="text-white text-xl font-bold">📅 Smart Calendar</Text>
            <Text className="text-gray-400 mt-1">ATLAS scansiona le email ogni 1 ora e salva le visite sul calendario.</Text>
          </View>
          <Switch value={calendarEnabled} onValueChange={setCalendarEnabled} trackColor={{ false: "#333", true: "#7c3aed" }} thumbColor="#fff"/>
        </View>

        <View className="bg-[rgba(255,255,255,0.06)] p-5 rounded-3xl mb-4 flex-row justify-between items-center border border-white/5">
          <View className="flex-1 pr-4">
            <Text className="text-white text-xl font-bold">☔ Ombrello Smart</Text>
            <Text className="text-gray-400 mt-1">Notifica se sta per piovere (Controllo ogni 3 ore).</Text>
          </View>
          <Switch value={umbrellaEnabled} onValueChange={setUmbrellaEnabled} trackColor={{ false: "#333", true: "#06b6d4" }} thumbColor="#fff" />
        </View>

        <View className="bg-[rgba(255,255,255,0.06)] p-5 rounded-3xl mb-10 flex-row justify-between items-center border border-white/5">
          <View className="flex-1 pr-4">
            <Text className="text-white text-xl font-bold">💊 Promemoria Pillola</Text>
            <Text className="text-gray-400 mt-1">Avviso quotidiano salute famiglia.</Text>
          </View>
          <Switch value={pillsEnabled} onValueChange={setPillsEnabled} trackColor={{ false: "#333", true: "#7c3aed" }} thumbColor="#fff" />
        </View>

      </ScrollView>
    </SafeAreaView>
  );
}
