import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  TextInput,
  ScrollView,
  SafeAreaView,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
  Alert,
  Image,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import Animated, { FadeInUp, FadeIn } from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import {
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
} from 'expo-audio';
import * as FileSystem from 'expo-file-system/legacy';
import * as ImagePicker from 'expo-image-picker';
import * as Speech from 'expo-speech';
import Markdown from 'react-native-markdown-display';
import AsyncStorage from '@react-native-async-storage/async-storage';
import apiService, { ApiError, type EmailDraft } from '../services/api';
import { syncUpcomingReminders } from '../services/notifications';
import { useAuth } from '../../App';

interface ChatMsg {
  role: 'user' | 'ai';
  text: string;
  ts?: number;
  imageUri?: string;
}

interface PendingImage {
  uri: string;
  base64: string;
  mimeType: string;
}

const MAX_IMAGE_BASE64 = 13_000_000; // ~9,7 MB reali, sotto il limite di 10 MB del backend

/** Riconosce il formato dai magic byte base64 (Android/iOS possono restituire PNG o HEIC). */
function detectImageMime(base64: string): string {
  if (base64.startsWith('/9j/')) return 'image/jpeg';
  if (base64.startsWith('iVBORw0KGgo')) return 'image/png';
  if (base64.startsWith('UklGR')) return 'image/webp';
  if (base64.startsWith('AAAAIGZ0eXB')) return 'image/heic';
  return 'image/jpeg';
}

const WELCOME: ChatMsg = {
  role: 'ai',
  text: `Ciao! Sono **ATLAS AI**. Chiedimi meteo, email, calendario, budget o italiano.`,
};

/** Il markdown non va letto ad alta voce: via i marcatori, restano le parole. */
function testoPerVoce(text: string): string {
  return text
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/[*_`#>]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/** Expo Haptics non esiste sul web: un errore qui non deve bloccare l'invio. */
function fireHaptic(call: () => Promise<unknown>) {
  if (Platform.OS === 'web') return;
  try {
    void call().catch(() => undefined);
  } catch {
    // Alcuni dispositivi non supportano l'haptic feedback.
  }
}

export default function ChatScreen({ route }: any) {
  const { profileId: authProfileId, authToken } = useAuth();
  const profileId: string = route?.params?.profileId ?? authProfileId ?? 'io';

  const [messages, setMessages] = useState<ChatMsg[]>([WELCOME]);
  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [pendingImage, setPendingImage] = useState<PendingImage | null>(null);
  const scrollViewRef = useRef<ScrollView>(null);
  const audioRecorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  // Se l'utente ha già scritto, la cronologia del server non deve sovrascrivere.
  const sentRef = useRef(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Array<{ ruolo: string; testo: string; quando?: string | null }>>([]);
  const [searching, setSearching] = useState(false);
  const [speakingIndex, setSpeakingIndex] = useState<number | null>(null);
  const [emailDraft, setEmailDraft] = useState<EmailDraft | null>(null);
  // Indice realmente in lettura: i callback di Speech.speak arrivano in ritardo,
  // quindi un messaggio vecchio non deve azzerare lo stato di quello nuovo.
  const speakingRef = useRef<number | null>(null);

  // Nessuna voce deve continuare a parlare dopo aver lasciato la chat.
  useEffect(() => {
    return () => {
      Speech.stop().catch(() => {});
    };
  }, []);

  const stopSpeaking = () => {
    speakingRef.current = null;
    setSpeakingIndex(null);
  };

  // Bozza Gmail: caricata all'apertura e dopo ogni risposta, perché il modello
  // può prepararne una ma non può inviarla.
  useEffect(() => {
    let active = true;
    apiService
      .getEmailDraft()
      .then((result) => {
        if (active) setEmailDraft(result.data ?? null);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [profileId, isLoading]);

  const confirmEmailDraft = async () => {
    try {
      const result = await apiService.sendEmailDraft();
      setEmailDraft(null);
      Alert.alert(result.status === 'ok' ? 'Email inviata' : 'Invio non riuscito', result.message || '');
    } catch (error: any) {
      Alert.alert('Invio non riuscito', error?.message || 'Riprova.');
    }
  };

  const discardEmailDraft = async () => {
    try {
      await apiService.discardEmailDraft();
    } catch {
      // se il backend non risponde la bozza resta: meglio non perdere nulla
    }
    setEmailDraft(null);
  };

  const toggleSpeech = async (index: number, text: string) => {
    const clean = testoPerVoce(text);
    if (!clean) return;
    if (speakingRef.current === index) {
      await Speech.stop();
      stopSpeaking();
      return;
    }
    await Speech.stop();
    speakingRef.current = index;
    setSpeakingIndex(index);
    Speech.speak(clean, {
      language: 'it-IT',
      onDone: () => {
        if (speakingRef.current === index) stopSpeaking();
      },
      onStopped: () => {
        if (speakingRef.current === index) stopSpeaking();
      },
      onError: () => {
        if (speakingRef.current === index) stopSpeaking();
      },
    });
  };

  // Cronologia locale per profilo.
  useEffect(() => {
    (async () => {
      try {
        const raw = await AsyncStorage.getItem(`@atlas/history/${profileId}`);
        if (raw) {
          const parsed = JSON.parse(raw);
          if (Array.isArray(parsed) && parsed.length) {
            // Se l'utente ha già scritto mentre caricavamo, non sovrascrivere.
            setMessages((previous) => (previous.length <= 1 ? parsed : previous));
          }
        }
      } catch {
        // prima apertura
      }
    })();
  }, [profileId]);

  useEffect(() => {
    if (messages.length <= 1) return;
    // Il file locale della foto non è persistente: salviamo solo il testo.
    const persistibile = messages.map(({ imageUri, ...rest }) => rest);
    AsyncStorage.setItem(`@atlas/history/${profileId}`, JSON.stringify(persistibile)).catch(() => {});
  }, [messages, profileId]);

  // Cronologia sincronizzata: la stessa su tutti i dispositivi (backend).
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const result = await apiService.getChatHistory(undefined, 40);
        const rows = Array.isArray(result.data) ? result.data : [];
        if (!active || !rows.length || sentRef.current) return;
        setMessages([
          WELCOME,
          ...rows
            .filter((row) => (row.testo || '').trim())
            .map((row) => ({ role: row.ruolo === 'user' ? ('user' as const) : ('ai' as const), text: row.testo })),
        ]);
      } catch {
        // Offline: resta la cronologia salvata sul dispositivo.
      }
    })();
    return () => {
      active = false;
    };
  }, [profileId]);

  const runSearch = async () => {
    setSearching(true);
    try {
      const result = await apiService.getChatHistory(searchQuery, 50);
      setSearchResults(Array.isArray(result.data) ? result.data : []);
    } catch (error: any) {
      Alert.alert('Ricerca non disponibile', error?.message ?? 'Riprova quando torni online.');
    } finally {
      setSearching(false);
    }
  };

  // Scenario precompilato (es. dalla schermata Italiano).
  useEffect(() => {
    const prompt = route?.params?.initialPrompt;
    if (typeof prompt === 'string' && prompt.trim()) {
      setInputText(prompt.trim());
    }
  }, [route?.params?.initialPrompt]);

  // Rilascia il microfono se si esce dalla schermata durante la registrazione.
  useEffect(() => {
    return () => {
      // Ferma una registrazione rimasta attiva se si cambia schermata.
      audioRecorder.stop().catch(() => {});
    };
  }, [audioRecorder]);

  const startRecording = async () => {
    if (isRecording || isTranscribing) return;
    try {
      const permission = await requestRecordingPermissionsAsync();
      if (!permission.granted) {
        Alert.alert(
          'Microfono non autorizzato',
          'Consenti l\'accesso al microfono dalle impostazioni del dispositivo per dettare i messaggi.'
        );
        return;
      }
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      await audioRecorder.prepareToRecordAsync();
      audioRecorder.record();
      setIsRecording(true);
      fireHaptic(() => Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium));
    } catch (error: any) {
      Alert.alert('Registrazione non disponibile', error?.message ?? 'Riprova tra un istante.');
    }
  };

  const stopRecording = async () => {
    if (!isRecording) return;
    setIsRecording(false);
    fireHaptic(() => Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success));

    try {
      await audioRecorder.stop();
      await setAudioModeAsync({ allowsRecording: false });
      const uri = audioRecorder.uri;
      if (!uri) {
        Alert.alert('Audio non disponibile', 'Non sono riuscito a leggere la registrazione.');
        return;
      }

      setIsTranscribing(true);
      const base64 = await FileSystem.readAsStringAsync(uri, {
        encoding: FileSystem.EncodingType.Base64,
      });
      const result = await apiService.transcribeAudio(base64, 'audio/mp4');
      setInputText((previous) => (previous ? `${previous} ${result.testo}` : result.testo));
    } catch (error: any) {
      const message =
        error instanceof ApiError
          ? error.message
          : 'Trascrizione non riuscita. Riprova o scrivi il messaggio.';
      Alert.alert('Dettatura non disponibile', message);
    } finally {
      setIsTranscribing(false);
    }
  };

  const pickImage = async () => {
    if (isLoading || isTranscribing) return;
    try {
      const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) {
        Alert.alert(
          'Galleria non autorizzata',
          'Consenti l\'accesso alle foto dalle impostazioni del dispositivo per inviare immagini ad ATLAS.'
        );
        return;
      }
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        allowsEditing: false,
        quality: 0.65,
        base64: true,
        exif: false,
      });
      if (result.canceled) return;
      const asset = result.assets?.[0];
      if (!asset?.uri || !asset.base64) {
        Alert.alert('Foto non leggibile', 'Non sono riuscito a leggere questa immagine. Scegline un\'altra.');
        return;
      }
      if (asset.base64.length > MAX_IMAGE_BASE64) {
        Alert.alert('Foto troppo grande', 'Scegli una foto più piccola (max circa 10 MB).');
        return;
      }
      setPendingImage({
        uri: asset.uri,
        base64: asset.base64,
        mimeType: detectImageMime(asset.base64),
      });
      fireHaptic(() => Haptics.selectionAsync());
    } catch (error: any) {
      Alert.alert('Galleria non disponibile', error?.message ?? 'Riprova tra un istante.');
    }
  };

  const sendMessage = async () => {
    const text = inputText.trim();
    const caption = text || (pendingImage ? 'Cosa vedi in questa foto?' : '');
    if ((!caption && !pendingImage) || isLoading) return;
    sentRef.current = true;
    fireHaptic(() => Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light));
    setMessages((previous) => [
      ...previous,
      { role: 'user', text: caption, ts: Date.now(), imageUri: pendingImage?.uri },
    ]);
    const immagine = pendingImage
      ? { base64: pendingImage.base64, mimeType: pendingImage.mimeType }
      : undefined;
    setInputText('');
    setPendingImage(null);
    setIsLoading(true);

    try {
      const data = await apiService.sendMessage(caption, profileId, authToken || undefined, immagine);
      const reply = data?.reply ?? 'Nessuna risposta dal server.';
      setMessages((previous) => [
        ...previous,
        {
          role: 'ai',
          text: reply,
          ts: Date.now(),
        },
      ]);
      const reminderCreated =
        /promemoria (impostato|creato|salvato)|(impostato|creato|salvato).{0,40}promemoria/i.test(reply);
      const sync = await syncUpcomingReminders();
      if (reminderCreated && (!sync.ok || sync.scheduled === 0)) {
        setMessages((previous) => [
          ...previous,
          {
            role: 'ai',
            text: `⚠️ **Promemoria salvato, ma notifica non attiva:** ${sync.message}`,
            ts: Date.now(),
          },
        ]);
      }
      fireHaptic(() => Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success));
    } catch (error: any) {
      let message = error?.message || 'Errore di connessione.';
      if (error instanceof ApiError && error.status === 401) {
        message = 'Sessione scaduta: torna ai profili e inserisci di nuovo il PIN.';
      }
      setMessages((previous) => [
        ...previous,
        { role: 'ai', text: `⚠️ **Errore:** ${message}`, ts: Date.now() },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const markdownStyles = {
    body: { color: '#f0f0f5', fontSize: 17, lineHeight: 26 },
    heading1: { color: '#ffffff', fontSize: 22, fontWeight: '800' as const },
    heading2: { color: '#ffffff', fontSize: 19, fontWeight: '700' as const },
    strong: { fontWeight: '800' as const, color: '#ffffff' },
    em: { fontStyle: 'italic' as const, color: '#a5b4fc' },
    code_inline: { backgroundColor: '#ffffff15', color: '#67e8f9', padding: 4, borderRadius: 6 },
    fence: { backgroundColor: '#ffffff08', padding: 12, borderRadius: 12, marginVertical: 8 },
    blockquote: { borderLeftWidth: 3, borderLeftColor: '#7c3aed', paddingLeft: 12, marginVertical: 8 },
    link: { color: '#06b6d4' },
    list_item: { marginVertical: 2 },
  };

  return (
    <SafeAreaView className="flex-1 bg-[#0a0a0f]">
      <StatusBar style="light" />
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} className="flex-1">
        <View className="flex-row justify-between items-center px-5 py-4 border-b border-[#ffffff10] bg-[#0a0a0f]/90">
          <View className="bg-[#ffffff10] px-4 py-2 rounded-xl">
            <Text className="text-white font-bold">🧠</Text>
          </View>
          <View className="items-center">
            <Text className="text-lg font-black text-white">🧠 ATLAS</Text>
            <Text className="text-[#7c3aed] text-xs font-bold uppercase">{(profileId || '').toUpperCase()}</Text>
          </View>
          <View className="flex-row">
            <TouchableOpacity
              onPress={() => setSearchOpen(true)}
              accessibilityRole="button"
              accessibilityLabel="Cerca nella cronologia"
              className="bg-[#ffffff10] p-2 rounded-xl mr-2"
            >
              <Text className="text-white text-sm">🔍</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => {
                AsyncStorage.removeItem(`@atlas/history/${profileId}`).catch(() => {});
                setMessages([WELCOME]);
              }}
              className="bg-[#ffffff10] p-2 rounded-xl"
            >
              <Text className="text-white text-sm">🗑️</Text>
            </TouchableOpacity>
          </View>
        </View>

        {searchOpen ? (
          <View className="absolute inset-0 bg-[#0a0a0f] z-50 px-5 pt-5">
            <View className="flex-row items-center mb-4">
              <Text className="text-white text-xl font-black flex-1">🕘 Cronologia</Text>
              <TouchableOpacity onPress={() => setSearchOpen(false)} className="bg-[#ffffff10] p-2 rounded-xl">
                <Text className="text-white">✕</Text>
              </TouchableOpacity>
            </View>
            <View className="flex-row items-center mb-4">
              <TextInput
                className="flex-1 bg-[#ffffff08] text-white px-4 py-3 rounded-2xl border border-[#ffffff10] mr-2"
                placeholder="Cerca nelle conversazioni…"
                placeholderTextColor="#8888a0"
                value={searchQuery}
                onChangeText={setSearchQuery}
                onSubmitEditing={runSearch}
                returnKeyType="search"
              />
              <TouchableOpacity onPress={runSearch} className="bg-[#7c3aed] px-4 py-3 rounded-2xl">
                <Text className="text-white font-bold">{searching ? '…' : 'Cerca'}</Text>
              </TouchableOpacity>
            </View>
            <ScrollView className="flex-1" keyboardShouldPersistTaps="handled">
              {searchResults.length ? (
                searchResults.map((row, index) => (
                  <TouchableOpacity
                    key={`${row.quando ?? index}-${index}`}
                    onPress={() => {
                      if (row.ruolo === 'user') setInputText(row.testo);
                      setSearchOpen(false);
                    }}
                    className="bg-[#ffffff08] p-4 rounded-2xl mb-3 border border-[#ffffff10]"
                  >
                    <Text className="text-[#a78bfa] text-xs font-bold uppercase mb-1">
                      {row.ruolo === 'user' ? 'Tu' : 'ATLAS'}
                    </Text>
                    <Text className="text-white" numberOfLines={4}>
                      {row.testo}
                    </Text>
                  </TouchableOpacity>
                ))
              ) : (
                <Text className="text-[#8888a0] mt-4">
                  {searching
                    ? 'Cerco…'
                    : 'Scrivi una parola e premi Cerca: trovi i messaggi di tutti i tuoi dispositivi.'}
                </Text>
              )}
            </ScrollView>
          </View>
        ) : null}

        <ScrollView
          ref={scrollViewRef}
          onContentSizeChange={() => scrollViewRef.current?.scrollToEnd({ animated: true })}
          keyboardShouldPersistTaps="handled"
          className="flex-1 px-4 py-2"
        >
          {messages.map((message, index) => (
            <Animated.View
              key={index}
              entering={FadeInUp.delay(index * 15).springify()}
              className={`p-5 rounded-[28px] mb-4 max-w-[90%] ${
                message.role === 'user'
                  ? 'bg-[#7c3aed] self-end rounded-tr-sm'
                  : 'bg-[#1e1e2d] self-start rounded-tl-sm border border-[#ffffff08]'
              }`}
            >
              {message.imageUri ? (
                <Image
                  source={{ uri: message.imageUri }}
                  style={{ width: 220, height: 220, borderRadius: 18, marginBottom: 10 }}
                  resizeMode="cover"
                />
              ) : null}
              <Markdown style={markdownStyles}>{message.text}</Markdown>
              {message.role === 'ai' && testoPerVoce(message.text) ? (
                <TouchableOpacity
                  onPress={() => toggleSpeech(index, message.text)}
                  accessibilityRole="button"
                  accessibilityLabel={
                    speakingIndex === index ? 'Ferma la lettura ad alta voce' : 'Ascolta il messaggio'
                  }
                  className="flex-row items-center mt-3 self-start bg-[#ffffff10] px-3 py-2 rounded-full"
                >
                  <Text className="text-[#22d3ee] text-xs font-bold">
                    {speakingIndex === index ? '⏹ Ferma' : '🔊 Ascolta'}
                  </Text>
                </TouchableOpacity>
              ) : null}
            </Animated.View>
          ))}

          {isLoading && (
            <Animated.View
              entering={FadeIn}
              className="bg-[#1e1e2d] self-start p-5 rounded-[28px] rounded-tl-sm mb-4 border border-[#ffffff08] flex-row items-center"
            >
              <ActivityIndicator color="#06b6d4" size="small" />
              <Text className="text-[#8888a0] ml-3 font-bold">ATLAS sta pensando...</Text>
            </Animated.View>
          )}

          {isTranscribing && (
            <Animated.View
              entering={FadeIn}
              className="bg-[#1e1e2d] self-start p-5 rounded-[28px] rounded-tl-sm mb-4 border border-[#ffffff08] flex-row items-center"
            >
              <ActivityIndicator color="#7c3aed" size="small" />
              <Text className="text-[#8888a0] ml-3 font-bold">Trascrivo l'audio...</Text>
            </Animated.View>
          )}
        </ScrollView>

        <View className="px-4 py-3 bg-[#0a0a0f] border-t border-[#ffffff10] pb-8">
          {emailDraft ? (
            <View className="mb-3 bg-[#0e2a33] border border-[#22d3ee40] rounded-2xl p-3">
              <Text className="text-[#22d3ee] font-bold text-xs uppercase">
                Bozza email — non ancora inviata
              </Text>
              <Text className="text-white font-bold mt-1" numberOfLines={1}>
                {emailDraft.oggetto}
              </Text>
              <Text className="text-[#8888a0] text-xs" numberOfLines={1}>
                A: {emailDraft.destinatario}
                {emailDraft.allegato ? ` · 📎 ${emailDraft.allegato}` : ''}
              </Text>
              <View className="flex-row mt-2">
                <TouchableOpacity
                  onPress={confirmEmailDraft}
                  accessibilityRole="button"
                  accessibilityLabel="Invia la bozza di email"
                  className="bg-[#22d3ee] px-4 py-2 rounded-xl mr-2"
                >
                  <Text className="text-[#0a0a0f] font-bold text-sm">Invia</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={discardEmailDraft}
                  accessibilityRole="button"
                  accessibilityLabel="Scarta la bozza di email"
                  className="bg-[#ffffff10] px-4 py-2 rounded-xl"
                >
                  <Text className="text-white font-bold text-sm">Scarta</Text>
                </TouchableOpacity>
              </View>
            </View>
          ) : null}
          {pendingImage ? (
            <View className="flex-row items-center mb-3 bg-[#ffffff08] p-3 rounded-2xl border border-[#ffffff10]">
              <Image
                source={{ uri: pendingImage.uri }}
                style={{ width: 64, height: 64, borderRadius: 12 }}
                resizeMode="cover"
              />
              <View className="flex-1 ml-3">
                <Text className="text-white font-bold">Foto pronta</Text>
                <Text className="text-[#8888a0] text-xs">ATLAS la analizzerà</Text>
              </View>
              <TouchableOpacity
                onPress={() => setPendingImage(null)}
                className="bg-[#ef444420] px-3 py-2 rounded-xl"
              >
                <Text className="text-[#fca5a5] font-bold">✕</Text>
              </TouchableOpacity>
            </View>
          ) : null}
          <View className="flex-row items-center">
            <TouchableOpacity
              onPress={pickImage}
              disabled={isLoading || isTranscribing}
              accessibilityRole="button"
              accessibilityLabel="Invia una foto dalla galleria"
              className="w-12 h-12 rounded-full items-center justify-center mr-2 bg-[#ffffff15]"
            >
              <Text className="text-white text-xl">🖼️</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPressIn={startRecording}
              onPressOut={stopRecording}
              disabled={isTranscribing || isLoading}
              accessibilityRole="button"
              accessibilityLabel="Tieni premuto per dettare un messaggio"
              className={`w-14 h-14 rounded-full items-center justify-center mr-3 ${
                isRecording ? 'bg-[#ef4444]' : 'bg-[#ffffff15]'
              }`}
            >
              <Text className="text-white text-2xl">🎤</Text>
            </TouchableOpacity>

            <TextInput
              className="flex-1 bg-[#ffffff08] text-white px-5 py-4 rounded-[32px] text-[16px] mr-3 border border-[#ffffff10]"
              placeholder="Chiedi ad ATLAS..."
              placeholderTextColor="#8888a0"
              value={inputText}
              onChangeText={setInputText}
              multiline
            />
            <TouchableOpacity
              className={`w-14 h-14 rounded-full items-center justify-center ${
                inputText.trim() || pendingImage ? 'bg-[#7c3aed]' : 'bg-[#ffffff10]'
              }`}
              onPress={sendMessage}
              disabled={(!inputText.trim() && !pendingImage) || isLoading}
              accessibilityRole="button"
              accessibilityLabel="Invia messaggio"
            >
              <Text className="text-white text-2xl font-black">↑</Text>
            </TouchableOpacity>
          </View>
          {isRecording && (
            <View className="items-center mt-2">
              <Text className="text-[#ef4444] font-bold">🔴 Registrando... Rilascia per dettare</Text>
            </View>
          )}
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
