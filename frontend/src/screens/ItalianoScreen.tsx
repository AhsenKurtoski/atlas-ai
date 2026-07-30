import React from 'react';
import { View, Text, TouchableOpacity, ScrollView, SafeAreaView, Dimensions } from 'react-native';
import { StatusBar } from 'expo-status-bar';

const { width } = Dimensions.get('window');

export default function ItalianoScreen({ route }: any) {
  const profileLevel = route?.params?.profileLevel || "B1";
  
  return (
    <SafeAreaView className="flex-1 bg-[#0a0a0f]">
      <StatusBar style="light" />
      <ScrollView className="flex-1 p-5">
        
        <View className="flex-row justify-between items-center mb-8">
            <View>
              <Text className="text-4xl font-extrabold text-white">🇮🇹 Italiano</Text>
              <Text className="text-[#06b6d4] text-lg font-bold">Livello Famiglia: {profileLevel}</Text>
            </View>
            <View className="bg-[rgba(255,255,255,0.08)] p-3 rounded-2xl border border-[rgba(255,255,255,0.1)]">
                <Text className="text-white text-sm font-bold">Mamma 🔥5</Text>
                <Text className="text-white text-sm font-bold">Papà 🔥3</Text>
            </View>
        </View>

        {/* Lezione di Oggi - Gradient Card Simulation */}
        <View className="bg-[#1e1b4b] p-6 rounded-[32px] mb-6 border border-[#7c3aed] shadow-lg shadow-[#7c3aed]">
          <View className="bg-[#7c3aed] self-start px-3 py-1 rounded-full mb-4">
            <Text className="text-white font-bold text-xs uppercase tracking-widest">Lezione Quotidiana</Text>
          </View>
          <Text className="text-white text-3xl font-extrabold mb-2">Il Condizionale</Text>
          <Text className="text-[#a5b4fc] text-lg mb-6 leading-6">"Vorrei, potrei, farei" - Come chiedere le cose in modo educato e formale in Italia.</Text>
          
          <TouchableOpacity className="bg-white py-4 rounded-2xl items-center shadow-md">
            <Text className="text-[#4c1d95] font-black text-xl">Inizia Lezione (5 min) →</Text>
          </TouchableOpacity>
        </View>

        {/* Quiz Veloce */}
        <View className="bg-[#164e63] p-6 rounded-[32px] mb-8 border border-[#06b6d4] shadow-lg">
          <View className="bg-[#06b6d4] self-start px-3 py-1 rounded-full mb-4">
            <Text className="text-white font-bold text-xs uppercase tracking-widest">Sfida Famiglia</Text>
          </View>
          <Text className="text-white text-2xl font-extrabold mb-2">Quiz di 60 Secondi ⏱️</Text>
          <Text className="text-[#cffafe] text-lg mb-6">Metti alla prova la tua memoria e fai guadagnare 10 punti al tuo profilo!</Text>
          
          <TouchableOpacity className="bg-transparent py-4 rounded-2xl items-center border-2 border-white">
            <Text className="text-white font-black text-xl">Gioca Subito</Text>
          </TouchableOpacity>
        </View>

        {/* Situazioni Pratiche - Griglia */}
        <Text className="text-white text-2xl font-bold mb-5 ml-2">Simula Situazioni Reali</Text>
        <View className="flex-row flex-wrap justify-between">
            {[
              { icon: '🏥', title: 'Medico', color: 'bg-red-900/40 border-red-500/30' },
              { icon: '🏦', title: 'Banca', color: 'bg-green-900/40 border-green-500/30' },
              { icon: '🏫', title: 'Scuola', color: 'bg-yellow-900/40 border-yellow-500/30' },
              { icon: '🛒', title: 'Spesa', color: 'bg-blue-900/40 border-blue-500/30' }
            ].map((item, i) => (
                <TouchableOpacity key={i} className={`w-[48%] p-6 rounded-3xl items-center mb-4 border ${item.color}`}>
                    <Text className="text-5xl mb-2">{item.icon}</Text>
                    <Text className="text-white text-xl font-bold">{item.title}</Text>
                </TouchableOpacity>
            ))}
        </View>
        <View className="h-10" />

      </ScrollView>
    </SafeAreaView>
  );
}
