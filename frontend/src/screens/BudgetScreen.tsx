import React, { useCallback, useState } from 'react';
import { View, Text, ScrollView, SafeAreaView, TextInput, TouchableOpacity, Alert } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { useFocusEffect } from '@react-navigation/native';
import Animated, { FadeInUp } from 'react-native-reanimated';
import apiService, { BudgetData, BudgetReport } from '../services/api';
import { useAuth } from '../../App';

const CATEGORIES = ['🍕 Cibo', '🚗 Trasporti', '⚡ Bollette', '💊 Salute', '📚 Istruzione', '🎮 Svago', 'Altro'];

const formatEuro = (value: number) => value.toFixed(2).replace('.', ',');
const normalizeCategory = (value: string) => {
  const clean = (value || 'Altro').trim();
  return clean ? clean.charAt(0).toUpperCase() + clean.slice(1) : 'Altro';
};

export default function BudgetScreen({ route }: any) {
  const { profileId: authProfileId } = useAuth();
  const profileId: string = route?.params?.profileId ?? authProfileId ?? 'io';

  const [importo, setImporto] = useState('');
  const [categoria, setCategoria] = useState('');
  const [descrizione, setDescrizione] = useState('');
  const [budget, setBudget] = useState<BudgetData>({ totale: 0, dettaglio: [] });
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [report, setReport] = useState<BudgetReport | null>(null);
  const [limitDrafts, setLimitDrafts] = useState<Record<string, string>>({});
  const [savingLimits, setSavingLimits] = useState(false);

  const loadBudget = useCallback(async () => {
    const [budgetResult, reportResult] = await Promise.allSettled([
      apiService.getBudget(),
      apiService.getBudgetReport(),
    ]);
    try {
      if (budgetResult.status === 'fulfilled') {
        const data = budgetResult.value.data;
        if (data && Array.isArray(data.dettaglio)) {
          setBudget({ totale: Number(data.totale) || 0, dettaglio: data.dettaglio });
        } else {
          setBudget({ totale: 0, dettaglio: [] });
        }
      }
      if (reportResult.status === 'fulfilled' && reportResult.value.data) {
        const nuovoReport = reportResult.value.data;
        setReport(nuovoReport);
        setLimitDrafts((previous) => {
          if (Object.keys(previous).length) return previous;
          return Object.fromEntries(
            Object.entries(nuovoReport.soglie ?? {}).map(([category, value]) => [category, String(value)])
          );
        });
      }
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
    const category = normalizeCategory(row.categoria);
    acc[category] = (acc[category] || 0) + row.importo;
    return acc;
  }, {});

  const totale = budget.totale || Object.values(totali).reduce((sum, value) => sum + value, 0);

  const saveLimits = async () => {
    const limiti: Record<string, number> = {};
    Object.entries(limitDrafts).forEach(([category, value]) => {
      const parsed = parseFloat(String(value).replace(',', '.'));
      if (parsed > 0) limiti[category] = parsed;
    });
    setSavingLimits(true);
    try {
      await apiService.setBudgetLimits(limiti);
      await loadBudget();
      Alert.alert('Limiti salvati', `${Object.keys(limiti).length} categorie con un limite mensile.`);
    } catch (error: any) {
      Alert.alert('Limiti non salvati', error?.message ?? 'Riprova tra poco.');
    } finally {
      setSavingLimits(false);
    }
  };

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
      Alert.alert('Fatto', `Spesa €${formatEuro(parsed)} in "${categoria}" registrata.`);
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
        <Text className="text-[#22c55e] text-4xl font-black mb-6">€{formatEuro(totale)}</Text>
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
                    €{formatEuro(amount)} · {percentage.toFixed(0)}%
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

        {report?.avvisi?.length ? (
          <View className="bg-[#ef444415] border border-[#ef444440] p-5 rounded-[28px] mb-6">
            <Text className="text-[#fca5a5] font-bold text-lg mb-2">⚠️ Limiti superati</Text>
            {report.avvisi.map((avviso) => (
              <Text key={avviso} className="text-[#fca5a5] text-sm mb-1">
                • {avviso}
              </Text>
            ))}
          </View>
        ) : null}

        <View className="bg-[#ffffff08] p-5 rounded-[28px] mb-6">
          <Text className="text-white font-bold text-lg mb-1">🎯 Soglie mensili</Text>
          <Text className="text-[#8888a0] text-sm mb-4">
            {report
              ? `Mese ${report.mese} · €${formatEuro(report.totale)}` +
                (report.mese_precedente.totale
                  ? ` · mese scorso €${formatEuro(report.mese_precedente.totale)}`
                  : '')
              : 'Imposta un limite per categoria: ATLAS avvisa quando lo superi.'}
          </Text>

          {(report?.dettaglio?.length ? report.dettaglio.map((row) => row.categoria) : Object.keys(limitDrafts)).map(
            (category) => {
              const soglia = report?.soglie?.[category];
              const sforato = Boolean(report?.dettaglio?.find((row) => row.categoria === category)?.sforato);
              return (
                <View key={category} className="flex-row items-center mb-3">
                  <Text className={`flex-1 ${sforato ? 'text-[#fca5a5]' : 'text-white'}`}>
                    {category}
                    {soglia ? ` · limite €${formatEuro(soglia)}` : ''}
                  </Text>
                  <TextInput
                    className="bg-[#ffffff10] text-white px-3 py-2 rounded-xl w-28 text-right"
                    placeholder="nessuno"
                    placeholderTextColor="#888"
                    keyboardType="decimal-pad"
                    value={limitDrafts[category] ?? ''}
                    onChangeText={(value) =>
                      setLimitDrafts((previous) => ({ ...previous, [category]: value }))
                    }
                  />
                </View>
              );
            }
          )}

          <TouchableOpacity
            onPress={saveLimits}
            disabled={savingLimits}
            className={`p-3 rounded-2xl items-center mt-2 ${savingLimits ? 'bg-[#7c3aed80]' : 'bg-[#7c3aed]'}`}
          >
            <Text className="text-white font-black">
              {savingLimits ? 'Salvataggio...' : 'Salva soglie'}
            </Text>
          </TouchableOpacity>
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
