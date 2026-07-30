import React, { useState, useEffect } from 'react';
import { View, Text, ScrollView, SafeAreaView, TextInput, TouchableOpacity, Alert } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import Animated, { FadeInUp } from 'react-native-reanimated';
import apiService from '../services/api';

const CATEGORIES = ['🍕 Cibo', '🚗 Trasporti', '⚡ Bollette', '💊 Salute', '📚 Istruzione', '🎮 Svago', 'Altro'];

type Spesa = { cat: string; imp: number; desc?: string };

export default function BudgetScreen({ route }: any) {
  const profileId: string = route?.params?.profileId || 'io';
  const [importo, setImporto] = useState('');
  const [categoria, setCategoria] = useState('');
  const [descrizione, setDescrizione] = useState('');
  const [spese, setSpese] = useState<Spesa[]>([
    { cat: 'Cibo', imp: 45.5 },
    { cat: 'Trasporti', imp: 30.0 },
    { cat: 'Cibo', imp: 22.3 },
    { cat: 'Bollette', imp: 120.0 },
    { cat: 'Svago', imp: 15.0 },
  ]);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await apiService.getBudget();
        const d = res?.data;
        if (d?.dettaglio && Array.isArray(d.dettaglio)) {
          const mapped: Spesa[] = d.dettaglio.map((row: any) => ({
            cat: row.categoria || 'Altro',
            imp: Number(row.importo) || 0,
          }));
          if (mapped.length) setSpese(mapped);
        }
      } catch {
        // restano i mock iniziali
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const totali = spese.reduce((acc: Record<string, number>, s) => {
    acc[s.cat] = (acc[s.cat] || 0) + s.imp;
    return acc;
  }, {} as Record<string, number>);

  const totale = Object.values(totali).reduce((a, b) => a + b, 0);

  const saveSpesa = async () => {
    const imp = parseFloat(importo.replace(',', '.'));
    if (!imp || imp <= 0) {
      Alert.alert('Importo non valido', 'Inserisci un importo maggiore di 0.');
      return;
    }
    if (!categoria) {
      Alert.alert('Categoria mancante', 'Seleziona una categoria prima di salvare.');
      return;
    }
    setSaving(true);
    try {
      await apiService.addSpesa({
        importo: imp,
        categoria,
        descrizione: descrizione.trim(),
        slug: profileId,
      });
      const updated = [...spese, { cat: categoria, imp, desc: descrizione.trim() || undefined }];
      setSpese(updated);
      setImporto('');
      setCategoria('');
      setDescrizione('');
      Alert.alert('Fatto', `Spesa €${imp.toFixed(2)} in "${categoria}" registrata.`);
    } catch (e: any) {
      Alert.alert('Errore', e?.message || 'Impossibile salvare la spesa.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView className="flex-1 bg-[#0a0a0f]">
      <StatusBar style="light" />
      <ScrollView className="flex-1 p-5">
        <Text className="text-3xl font-black text-white mb-2">💰 Budget Famiglia</Text>
        <Text className="text-[#22c55e] text-4xl font-black mb-6">
          €{totale.toFixed(2)}
        </Text>
        {loading ? (
          <Text className="text-[#8888a0] mb-6">Aggiornamento dati dal backend...</Text>
        ) : null}

        <View className="bg-[#ffffff08] p-5 rounded-[28px] mb-6">
          <Text className="text-white font-bold text-lg mb-4">Spese per Categoria</Text>
          {Object.entries(totali).map(([cat, imp], i) => {
            const pct = totale ? (imp / totale) * 100 : 0;
            return (
              <Animated.View key={cat} entering={FadeInUp.delay(i * 100)} className="mb-4">
                <View className="flex-row justify-between mb-1">
                  <Text className="text-white font-semibold">{cat}</Text>
                  <Text className="text-[#8888a0]">€{imp.toFixed(2)} · {pct.toFixed(0)}%</Text>
                </View>
                <View className="bg-[#ffffff10] h-3 rounded-full overflow-hidden">
                  <View
                    className="h-full rounded-full bg-gradient-to-r from-[#7c3aed] to-[#06b6d4]"
                    style={{ width: `${pct}%` }}
                  />
                </View>
              </Animated.View>
            );
          })}
          {!Object.keys(totali).length ? (
            <Text className="text-[#8888a0]">Nessuna spesa registrata. Inizia qui sotto ⬇️</Text>
          ) : null}
        </View>

        <View className="bg-[#ffffff08] p-5 rounded-[28px] mb-10">
          <Text className="text-white font-bold text-lg mb-4">➕ Nuova Spesa</Text>

          <TextInput
            className="bg-[#ffffff10] text-white p-4 rounded-2xl mb-3 text-lg"
            placeholder="Importo (€)"
            placeholderTextColor="#888"
            keyboardType="numeric"
            value={importo}
            onChangeText={setImporto}
          />

          <ScrollView horizontal className="mb-3">
            {CATEGORIES.map((c) => {
              const clean = c.replace(/[^\w\sÀ-ÿ]/g, '').trim();
              const selected = categoria === clean;
              return (
                <TouchableOpacity
                  key={c}
                  onPress={() => setCategoria(clean)}
                  className={`px-4 py-2 rounded-full mr-2 ${selected ? 'bg-[#7c3aed]' : 'bg-[#ffffff15]'}`}
                >
                  <Text className="text-white font-semibold">{c}</Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>

          <TextInput
            className="bg-[#ffffff10] text-white p-4 rounded-2xl mb-4 text-lg"
            placeholder="Descrizione (opzionale)"
            placeholderTextColor="#888"
            value={descrizione}
            onChangeText={setDescrizione}
          />

          <TouchableOpacity
            onPress={saveSpesa}
            disabled={saving}
            className={`py-4 rounded-2xl items-center ${saving ? 'bg-[#22c55e99]' : 'bg-[#22c55e]'}`}
          >
            <Text className="text-white font-black text-lg">
              {saving ? 'Salvataggio...' : '✅ Aggiungi Spesa'}
            </Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
