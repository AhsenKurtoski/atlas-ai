import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Platform,
  RefreshControl,
  SafeAreaView,
  ScrollView,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { useFocusEffect } from '@react-navigation/native';
import apiService, { TodoRow } from '../services/api';
import { syncUpcomingReminders } from '../services/notifications';

// Alert.alert su React Native Web ignora i pulsanti: senza questo fallback le
// azioni distruttive (elimina/svuota) resterebbero bloccate nel browser.
const confirmDestructive = (title: string, message: string, confirmLabel = 'Elimina') =>
  new Promise<boolean>((resolve) => {
    const webConfirm =
      Platform.OS === 'web' && typeof globalThis !== 'undefined'
        ? (globalThis as any).confirm
        : null;
    if (typeof webConfirm === 'function') {
      resolve(Boolean(webConfirm(`${title}\n\n${message}`)));
      return;
    }
    Alert.alert(title, message, [
      { text: 'Annulla', style: 'cancel', onPress: () => resolve(false) },
      { text: confirmLabel, style: 'destructive', onPress: () => resolve(true) },
    ]);
  });

export default function ListaSpesaScreen({ navigation }: any) {
  const [todos, setTodos] = useState<TodoRow[]>([]);
  const [task, setTask] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const response = await apiService.getTodos();
      setTodos(response.data ?? []);
      setError('');
    } catch (err: any) {
      setError(err?.message ?? 'Lista non disponibile.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const pending = todos.filter((todo) => !todo.done);
  const completed = todos.filter((todo) => todo.done);

  const addTask = async () => {
    const value = task.trim();
    if (!value || busy) return;
    setBusy(true);
    try {
      await apiService.addTodo(value);
      setTask('');
      await load();
      // La lista è allegata ai promemoria spesa: aggiorna subito la notifica
      // locale così il telefono mostra le cose appena aggiunte.
      await syncUpcomingReminders();
    } catch (err: any) {
      Alert.alert('Non aggiunto', err?.message ?? 'Riprova tra poco.');
    } finally {
      setBusy(false);
    }
  };

  const completeTask = async (todo: TodoRow) => {
    const index = todos.findIndex((row) => row.id === todo.id) + 1;
    if (index <= 0) return;
    try {
      await apiService.completeTodoByIndex(index);
      await load();
      await syncUpcomingReminders();
    } catch (err: any) {
      Alert.alert('Non completato', err?.message ?? 'Riprova tra poco.');
    }
  };

  const removeTask = async (todo: TodoRow) => {
    const index = todos.findIndex((row) => row.id === todo.id) + 1;
    if (index <= 0) return;
    const confirmed = await confirmDestructive(
      'Eliminare questo elemento?',
      todo.task ?? 'Elemento della lista'
    );
    if (!confirmed) return;
    try {
      await apiService.deleteTodoByIndex(index);
      await load();
      await syncUpcomingReminders();
    } catch (err: any) {
      Alert.alert('Non eliminato', err?.message ?? 'Riprova tra poco.');
    }
  };

  const clearCompleted = async () => {
    if (!completed.length) return;
    const confirmed = await confirmDestructive(
      'Svuotare i completati?',
      `${completed.length} elementi verranno rimossi dalla lista.`,
      'Svuota'
    );
    if (!confirmed) return;
    try {
      // Dal fondo: gli indici precedenti non cambiano mentre eliminiamo.
      const indices = todos
        .map((todo, index) => ({ todo, index: index + 1 }))
        .filter((item) => item.todo.done)
        .map((item) => item.index)
        .sort((a, b) => b - a);
      for (const index of indices) {
        await apiService.deleteTodoByIndex(index);
      }
      await load();
      await syncUpcomingReminders();
    } catch (err: any) {
      Alert.alert('Pulizia non completata', err?.message ?? 'Riprova tra poco.');
    }
  };

  const row = (todo: TodoRow, index: number, done: boolean) => (
    <View
      key={todo.id ?? `${todo.task}-${index}`}
      className={`flex-row items-center p-4 rounded-2xl mb-3 border ${
        done ? 'bg-[#ffffff04] border-[#ffffff08]' : 'bg-[#ffffff08] border-[#ffffff10]'
      }`}
    >
      <TouchableOpacity
        onPress={() => !done && completeTask(todo)}
        disabled={done}
        accessibilityRole="button"
        accessibilityLabel={done ? 'Completato' : `Completa ${todo.task ?? 'task'}`}
        className={`w-9 h-9 rounded-full items-center justify-center mr-3 ${
          done ? 'bg-[#22c55e20]' : 'bg-[#7c3aed]'
        }`}
      >
        <Text className={`font-black ${done ? 'text-[#22c55e]' : 'text-white'}`}>{done ? '✓' : '○'}</Text>
      </TouchableOpacity>
      <View className="flex-1 pr-3">
        <Text className={`text-base font-bold ${done ? 'text-[#8888a0] line-through' : 'text-white'}`}>
          {todo.task ?? 'Task senza nome'}
        </Text>
        <Text className="text-[#8888a0] text-xs mt-1">
          {todo.assegnato_a && todo.assegnato_a !== 'Tutti' ? `Per ${todo.assegnato_a}` : 'Lista condivisa'}
        </Text>
      </View>
      <TouchableOpacity onPress={() => removeTask(todo)} className="p-2" accessibilityLabel="Elimina elemento">
        <Text className="text-[#fca5a5] text-lg">🗑️</Text>
      </TouchableOpacity>
    </View>
  );

  return (
    <SafeAreaView className="flex-1 bg-[#0a0a0f]">
      <StatusBar style="light" />
      <View className="flex-row items-center px-5 py-4 border-b border-[#ffffff10]">
        <TouchableOpacity onPress={() => navigation?.goBack?.()} className="w-10 h-10 rounded-xl bg-[#ffffff10] items-center justify-center mr-3">
          <Text className="text-white text-xl">←</Text>
        </TouchableOpacity>
        <View className="flex-1">
          <Text className="text-2xl font-black text-white">🛒 Lista spesa</Text>
          <Text className="text-[#8888a0] text-sm mt-1">
            {pending.length} da comprare · {completed.length} completati
          </Text>
        </View>
      </View>

      <ScrollView
        className="flex-1 px-5"
        keyboardShouldPersistTaps="handled"
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => {
              setRefreshing(true);
              load();
            }}
            tintColor="#7c3aed"
          />
        }
      >
        <View className="flex-row items-center mt-5 mb-6">
          <TextInput
            className="flex-1 bg-[#ffffff08] text-white px-4 py-4 rounded-2xl border border-[#ffffff10] mr-3"
            placeholder="Aggiungi latte, pane, frutta…"
            placeholderTextColor="#8888a0"
            value={task}
            onChangeText={setTask}
            onSubmitEditing={addTask}
            returnKeyType="done"
            maxLength={500}
          />
          <TouchableOpacity
            onPress={addTask}
            disabled={!task.trim() || busy}
            className={`w-14 h-14 rounded-2xl items-center justify-center ${task.trim() ? 'bg-[#7c3aed]' : 'bg-[#ffffff10]'}`}
          >
            <Text className="text-white text-2xl font-black">{busy ? '…' : '+'}</Text>
          </TouchableOpacity>
        </View>

        {loading ? <ActivityIndicator color="#7c3aed" className="mt-10" /> : null}
        {error ? (
          <View className="bg-[#ef444415] border border-[#ef444440] p-4 rounded-2xl mb-4">
            <Text className="text-[#fca5a5]">{error}</Text>
          </View>
        ) : null}

        <Text className="text-white/60 text-xs uppercase font-bold tracking-widest mb-3">Da comprare</Text>
        {pending.length ? pending.map((todo) => row(todo, todos.findIndex((item) => item.id === todo.id) + 1, false)) : (
          <View className="bg-[#ffffff05] border border-[#ffffff08] p-5 rounded-2xl mb-6">
            <Text className="text-[#8888a0]">La lista è vuota. Aggiungi qualcosa o chiedilo in chat.</Text>
          </View>
        )}

        {completed.length ? (
          <>
            <View className="flex-row justify-between items-center mt-3 mb-3">
              <Text className="text-white/60 text-xs uppercase font-bold tracking-widest">Completati</Text>
              <TouchableOpacity onPress={clearCompleted}>
                <Text className="text-[#fca5a5] text-sm font-bold">Svuota</Text>
              </TouchableOpacity>
            </View>
            {completed.map((todo) => row(todo, todos.findIndex((item) => item.id === todo.id) + 1, true))}
          </>
        ) : null}
        <View className="h-10" />
      </ScrollView>
    </SafeAreaView>
  );
}