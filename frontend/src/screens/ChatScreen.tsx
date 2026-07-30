import React, { useState, useRef, useEffect } from 'react';
import { View, Text, TouchableOpacity, TextInput, ScrollView, SafeAreaView, KeyboardAvoidingView, Platform, ActivityIndicator } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import Animated, { FadeInUp, FadeIn } from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import { Audio } from 'expo-av';
import Markdown from 'react-native-markdown-display';
import AsyncStorage from '@react-native-async-storage/async-storage';
import apiService from '../services/api';
import CONFIG from '../config';
import { useAuth } from '../../App';

interface ChatMsg { role: 'user' | 'ai'; text: string; ts?: number; latencyMs?: number }

export default function ChatScreen({ route, navigation }: any) {
  const { profileId } = route.params;
  const { authToken } = useAuth();
  const [messages, setMessages] = useState<ChatMsg[]>([
    {
      role: 'ai',
      text: `Ciao! Sono **ATLAS AI**. Sono il tuo assistente personale. 

Chiedimi tutto! Posso:
- 💰 **Crypto**: Prezzi Bitcoin/Ethereum in tempo reale
- 🌤️ **Meteo**: Che tempo fa in qualsiasi città
- 🛒 **Lista spesa**: Aggiungere e leggere la spesa
- 📧 **Email**: Leggere la posta
- 📅 **Calendar**: Gestire appuntamenti
- 🔍 **Ricerca web**: Cercare su internet
- 💡 **Consigli**: Barzellette, suggerimenti

Prova a dirmi 📱: *"Quant'è il Bitcoin oggi?"*`,
    },
  ]);
  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const scrollViewRef = useRef<ScrollView>(null);
  const recordingRef = useRef<Audio.Recording | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const raw = await AsyncStorage.getItem(`@atlas/history/${profileId}`);
        if (raw) {
          const parsed = JSON.parse(raw);
          if (Array.isArray(parsed) && parsed.length) setMessages(parsed);
        }
      } catch { /* prima apertura */ }
    })();
  }, [profileId]);

  useEffect(() => {
    if (messages.length <= 1) return;
    AsyncStorage.setItem(`@atlas/history/${profileId}`, JSON.stringify(messages)).catch(() => {});
  }, [messages, profileId]);

  const startRecording = async () => {
    try {
      await Audio.requestPermissionsAsync();
      await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });
      const { recording } = await Audio.Recording.createAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
      recordingRef.current = recording;
      setIsRecording(true);
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    } catch (e) {
      console.error(e);
    }
  };

  const stopRecording = async () => {
    if (!recordingRef.current) return;
    setIsRecording(false);
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    try {
      await recordingRef.current.stopAndUnloadAsync();
      const uri = recordingRef.current.getURI();
      console.log('Audio registrato:', uri);
      setMessages(prev => [...prev, { role: 'user', text: '🎤 [Messaggio vocale inviato]', ts: Date.now() }]);
    } catch (e) {
      console.error(e);
    }
  };

  const sendMessage = async () => {
    if (!inputText.trim() || isLoading) return;
    const userText = inputText;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    const userMsg: ChatMsg = { role: 'user', text: userText, ts: Date.now() };
    setMessages(prev => [...prev, userMsg]);
    setInputText('');
    setIsLoading(true);

    try {
      const data = await apiService.sendMessage(userText, profileId, authToken || undefined);
      const replyText = data?.reply ?? 'Nessuna risposta dal server.';
      const aiMsg: ChatMsg = {
        role: 'ai',
        text: replyText,
        ts: Date.now(),
        latencyMs: typeof data.latency_ms === 'number' ? data.latency_ms : undefined,
      };
      setMessages(prev => [...prev, aiMsg]);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } catch (e: any) {
      const errMsg = e?.message
        ? `⚠️ **Errore:** ${e.message}`
        : '⚠️ **Errore di connessione.**\n\nAssicurati che il backend Python sia acceso e che telefono e PC siano sulla stessa rete Wi-Fi.';
      setMessages(prev => [...prev, { role: 'ai', text: errMsg, ts: Date.now() }]);
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
          <TouchableOpacity onPress={() => navigation.goBack()} className="bg-[#ffffff10] px-4 py-2 rounded-xl">
            <Text className="text-white font-bold">←</Text>
          </TouchableOpacity>
          <View className="items-center">
            <Text className="text-lg font-black text-white">🧠 ATLAS</Text>
            <Text className="text-[#7c3aed] text-xs font-bold uppercase">{(profileId || '').toUpperCase()}</Text>
          </View>
          <TouchableOpacity
            onPress={() => {
              AsyncStorage.removeItem(`@atlas/history/${profileId}`).catch(() => {});
              setMessages(messages.slice(0, 1));
            }}
            className="bg-[#ffffff10] p-2 rounded-xl"
          >
            <Text className="text-white text-sm">🗑️</Text>
          </TouchableOpacity>
        </View>

        <ScrollView
          ref={scrollViewRef}
          onContentSizeChange={() => scrollViewRef.current?.scrollToEnd({ animated: true })}
          className="flex-1 px-4 py-2"
        >
          {messages.map((m, i) => (
            <Animated.View
              key={i}
              entering={FadeInUp.delay(i * 15).springify()}
              className={`p-5 rounded-[28px] mb-4 max-w-[90%] ${
                m.role === 'user'
                  ? 'bg-[#7c3aed] self-end rounded-tr-sm'
                  : 'bg-[#1e1e2d] self-start rounded-tl-sm border border-[#ffffff08]'
              }`}
            >
              <Markdown style={markdownStyles}>{m.text}</Markdown>
              {m.latencyMs ? (
                <Text className="text-white/50 text-[10px] mt-2">{m.latencyMs.toFixed(0)} ms</Text>
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
        </ScrollView>

        <View className="px-4 py-3 bg-[#0a0a0f] border-t border-[#ffffff10] pb-8">
          <View className="flex-row items-center">
            <TouchableOpacity
              onPressIn={startRecording}
              onPressOut={stopRecording}
              className={`w-14 h-14 rounded-full items-center justify-center mr-3 ${isRecording ? 'bg-[#ef4444] animate-pulse' : 'bg-[#ffffff15]'}`}
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
              className={`w-14 h-14 rounded-full items-center justify-center ${inputText.trim() ? 'bg-[#7c3aed]' : 'bg-[#ffffff10]'}`}
              onPress={sendMessage}
              disabled={!inputText.trim() || isLoading}
            >
              <Text className="text-white text-2xl font-black">↑</Text>
            </TouchableOpacity>
          </View>
          {isRecording && (
            <View className="items-center mt-2">
              <Text className="text-[#ef4444] font-bold animate-pulse">🔴 Registrando... Rilascia per inviare</Text>
            </View>
          )}
        </View>

      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
