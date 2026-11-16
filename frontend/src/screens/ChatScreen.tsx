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
import { Audio } from 'expo-av';
import * as FileSystem from 'expo-file-system';
import * as ImagePicker from 'expo-image-picker';
import Markdown from 'react-native-markdown-display';
import AsyncStorage from '@react-native-async-storage/async-storage';
import apiService, { ApiError } from '../services/api';
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
  const recordingRef = useRef<Audio.Recording | null>(null);

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
      const recording = recordingRef.current;
      recordingRef.current = null;
      if (recording) {
        recording.stopAndUnloadAsync().catch(() => {});
      }
    };
  }, []);

  const startRecording = async () => {
    if (isRecording || isTranscribing) return;
    try {
      const permission = await Audio.requestPermissionsAsync();
      if (!permission.granted) {
        Alert.alert(
          'Microfono non autorizzato',
          'Consenti l\'accesso al microfono dalle impostazioni del dispositivo per dettare i messaggi.'
        );
        return;
      }
      await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });
      const { recording } = await Audio.Recording.createAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
      recordingRef.current = recording;
      setIsRecording(true);
      fireHaptic(() => Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium));
    } catch (error: any) {
      Alert.alert('Registrazione non disponibile', error?.message ?? 'Riprova tra un istante.');
    }
  };

  const stopRecording = async () => {
    const recording = recordingRef.current;
    if (!recording) return;
    recordingRef.current = null;
    setIsRecording(false);
    fireHaptic(() => Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success));

    try {
      await recording.stopAndUnloadAsync();
      await Audio.setAudioModeAsync({ allowsRecordingIOS: false });
      const uri = recording.getURI();
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
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
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
      const reminderCreated = /promemoria impostato|promemoria creato/i.test(reply);
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
