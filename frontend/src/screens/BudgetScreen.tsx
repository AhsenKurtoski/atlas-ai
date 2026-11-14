import React, { useCallback, useState } from 'react';
import { View, Text, ScrollView, SafeAreaView, TextInput, TouchableOpacity, Alert } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { useFocusEffect } from '@react-navigation/native';
import Animated, { FadeInUp } from 'react-native-reanimated';
import apiService, { BudgetData } from '../services/api';
import { useAuth } from '../../App';

const CATEGORIES = ['🍕 Cibo', '🚗 Trasporti', '⚡ Bollette', '💊 Salute', '📚 Istruzione', '🎮 Svago', 'Altro'];

export default function BudgetScreen({ route }: any) {
  const { profileId: authProfileId } = useAuth();
  const profileId: string = route?.params?.profileId ?? authProfileId ?? 'io';

  const [importo, setImporto] = useState('');
  const [categoria, setCategoria] = useState('');
  const [descrizione, setDescrizione] = useState('');
  const [budget, setBudget] = useState<BudgetData>({ totale: 0, dettaglio: [] });
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  const loadBudget = useCallback(async () => {
    try {
      const result = await apiService.getBudget();
      const data = result.data;
      if (data && Array.isArray(data.dettaglio)) {
        setBudget({ totale: Number(data.totale) || 0, dettaglio: data.dettaglio });
      } else {
        setBudget({ totale: 0, dettaglio: [] });
      }
    } catch {
      // Offline: manteniamo i dati già mostrati.
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      loadBudget();
    }, [loadBudget])
  );

  const totali = budget.dettaglio.reduce<Record<string, number>>((acc, row) => {
    acc[row.categoria] = (acc[row.categoria] || 0) + row.importo;
    return acc;
  }, {});

  const totale = budget.totale || Object.values(totali).reduce((sum, value) => sum + value, 0);

  const saveSpesa = async () => {
    const parsed = parseFloat(importo.replace(',', '.'));
    if (!parsed || parsed <= 0) {
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
        importo: parsed,
        categoria,
        descrizione: descrizione.trim(),
      });
      setImporto('');
      setCategoria('');
      setDescrizione('');
      await loadBudget();
      Alert.alert('Fatto', `Spesa €${parsed.toFixed(2)} in "${categoria}" registrata.`);
    } catch (error: any) {
      Alert.alert(
        'Errore',
        error?.message || `Impossibile salvare la spesa per il profilo ${profileId}.`
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView className="flex-1 bg-[#0a0a0f]">
      <StatusBar style="light" />
      <ScrollView className="flex-1 p-5">
        <Text className="text-3xl font-black text-white mb-2">💰 Budget Famiglia</Text>
        <Text className="text-[#22c55e] text-4xl font-black mb-6">€{totale.toFixed(2)}</Text>
        {loading ? <Text className="text-[#8888a0] mb-6">Aggiornamento dati dal backend...</Text> : null}

        <View className="bg-[#ffffff08] p-5 rounded-[28px] mb-6">
          <Text className="text-white font-bold text-lg mb-4">Spese per Categoria</Text>
          {Object.entries(totali).map(([category, amount], index) => {
            const percentage = totale ? (amount / totale) * 100 : 0;
            return (
              <Animated.View key={category} entering={FadeInUp.delay(index * 100)} className="mb-4">
                <View className="flex-row justify-between mb-1">
                  <Text className="text-white font-semibold">{category}</Text>
                  <Text className="text-[#8888a0]">
                    €{amount.toFixed(2)} · {percentage.toFixed(0)}%
                  </Text>
                </View>
                <View className="bg-[#ffffff10] h-3 rounded-full overflow-hidden">
                  <View
                    className="h-full rounded-full bg-gradient-to-r from-[#7c3aed] to-[#06b6d4]"
                    style={{ width: `${percentage}%` }}
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
            keyboardType="decimal-pad"
            value={importo}
            onChangeText={setImporto}
          />

          <ScrollView horizontal className="mb-3" showsHorizontalScrollIndicator={false}>
            {CATEGORIES.map((category) => {
              const clean = category.replace(/[^\w\sÀ-ÿ]/g, '').trim();
              const selected = categoria === clean;
              return (
                <TouchableOpacity
                  key={category}
                  onPress={() => setCategoria(clean)}
                  className={`px-4 py-2 rounded-full mr-2 ${selected ? 'bg-[#7c3aed]' : 'bg-[#ffffff15]'}`}
                >
                  <Text className="text-white font-semibold">{category}</Text>
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
