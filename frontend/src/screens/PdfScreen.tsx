import React, { useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  SafeAreaView,
  TextInput,
  TouchableOpacity,
  Alert,
  Platform,
  ActivityIndicator,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import * as FileSystem from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import apiService from '../services/api';

function downloadOnWeb(base64: string, filename: string): void {
  const doc = (globalThis as any).document;
  const atobFn = (globalThis as any).atob;
  if (!doc || typeof atobFn !== 'function') {
    throw new Error('Download non disponibile in questo browser.');
  }
  const binary = atobFn(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  const url = (globalThis as any).URL.createObjectURL(
    new Blob([bytes], { type: 'application/pdf' })
  );
  const link = doc.createElement('a');
  link.href = url;
  link.download = filename;
  doc.body.appendChild(link);
  link.click();
  link.remove();
  (globalThis as any).URL.revokeObjectURL(url);
}

export default function PdfScreen() {
  const [titolo, setTitolo] = useState('Documento ATLAS');
  const [contenuto, setContenuto] = useState('');
  const [busy, setBusy] = useState(false);
  const [lastFile, setLastFile] = useState('');

  const genera = async () => {
    const cleanTitle = titolo.trim();
    const cleanBody = contenuto.trim();
    if (!cleanTitle) {
      Alert.alert('Titolo mancante', 'Inserisci un titolo per il documento.');
      return;
    }
    if (!cleanBody) {
      Alert.alert('Contenuto mancante', 'Scrivi il testo da includere nel PDF.');
      return;
    }

    setBusy(true);
    setLastFile('');
    try {
      const result = await apiService.createPdf(cleanTitle, cleanBody);
      const data = result.data;
      if (result.status !== 'ok' || !data?.base64) {
        throw new Error(result.message || 'Il backend non ha restituito il PDF.');
      }

      if (Platform.OS === 'web') {
        downloadOnWeb(data.base64, data.filename);
        setLastFile(`${data.filename} · ${Math.round(data.size / 1024)} KB`);
        return;
      }

      const available = await Sharing.isAvailableAsync();
      if (!available) {
        throw new Error('La condivisione file non è disponibile su questo dispositivo.');
      }
      const directory = FileSystem.cacheDirectory ?? FileSystem.documentDirectory;
      if (!directory) {
        throw new Error('Memoria temporanea non disponibile.');
      }
      const uri = `${directory}${data.filename}`;
      await FileSystem.writeAsStringAsync(uri, data.base64, {
        encoding: FileSystem.EncodingType.Base64,
      });
      await Sharing.shareAsync(uri, {
        mimeType: 'application/pdf',
        dialogTitle: 'Condividi o salva il PDF',
        UTI: 'com.adobe.pdf',
      });
      setLastFile(`${data.filename} · ${Math.round(data.size / 1024)} KB`);
    } catch (error: any) {
      Alert.alert('PDF non generato', error?.message ?? 'Riprova tra poco.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <SafeAreaView className="flex-1 bg-[#0a0a0f]">
      <StatusBar style="light" />
      <ScrollView className="flex-1 p-5" keyboardShouldPersistTaps="handled">
        <Text className="text-3xl font-black text-white mb-2">📄 Crea un PDF</Text>
        <Text className="text-[#8888a0] mb-6">
          Genera un documento A4 reale sul backend e condividilo con l'app Share di iOS o Android.
          Nessun servizio esterno e nessun file lasciato sul server.
        </Text>

        <View className="bg-[#ffffff08] p-5 rounded-[28px] mb-5 border border-[#7c3aed30]">
          <Text className="text-white font-bold mb-2">Titolo</Text>
          <TextInput
            className="bg-[#ffffff10] text-white p-4 rounded-2xl mb-4 text-lg"
            placeholder="Es. Riepilogo spese di novembre"
            placeholderTextColor="#888"
            value={titolo}
            onChangeText={setTitolo}
            maxLength={120}
          />

          <Text className="text-white font-bold mb-2">Contenuto</Text>
          <TextInput
            className="bg-[#ffffff10] text-white p-4 rounded-2xl mb-4 text-base"
            placeholder="Scrivi qui il testo del documento…"
            placeholderTextColor="#888"
            value={contenuto}
            onChangeText={setContenuto}
            multiline
            textAlignVertical="top"
            style={{ minHeight: 240 }}
            maxLength={20000}
          />

          <TouchableOpacity
            onPress={genera}
            disabled={busy}
            className={`py-4 rounded-2xl items-center ${busy ? 'bg-[#7c3aed99]' : 'bg-[#7c3aed]'}`}
          >
            {busy ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text className="text-white font-black text-lg">📄 Genera PDF</Text>
            )}
          </TouchableOpacity>

          {lastFile ? (
            <Text className="text-[#22c55e] text-sm mt-4">✅ Ultimo file: {lastFile}</Text>
          ) : null}
        </View>

        <View className="bg-[#1e1b4b] p-5 rounded-[28px] mb-10 border border-[#7c3aed40]">
          <Text className="text-white font-bold mb-2">Cosa succede</Text>
          <Text className="text-[#a5b4fc] text-sm leading-6">
            1. Il backend valida il testo e crea un PDF A4 con Helvetica.{'\n'}
            2. L'app scarica il file e apre il pannello di condivisione del sistema.{'\n'}
            3. Su iOS puoi salvarlo in File, inviarlo per email o condividerlo; su Android puoi
            usare Drive, Gmail o qualsiasi app compatibile.
          </Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
