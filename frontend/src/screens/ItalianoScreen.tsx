import React, { useCallback, useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  SafeAreaView,
  Modal,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { useFocusEffect } from '@react-navigation/native';
import apiService, {
  ItalianProgress,
  LeaderboardRow,
  LessonData,
  QuizQuestion,
  QuizResult,
} from '../services/api';
import { useAuth } from '../../App';

const SCENARI = [
  { icon: '🏥', title: 'Medico', color: 'bg-red-900/40 border-red-500/30' },
  { icon: '🏦', title: 'Banca', color: 'bg-green-900/40 border-green-500/30' },
  { icon: '🏫', title: 'Scuola', color: 'bg-yellow-900/40 border-yellow-500/30' },
  { icon: '🛒', title: 'Spesa', color: 'bg-blue-900/40 border-blue-500/30' },
];

const SCENARIO_PROMPTS: Record<string, string> = {
  Medico:
    'Facciamo un roleplay in italiano: tu sei il medico e io il paziente. Inizia tu con una domanda semplice.',
  Banca:
    'Facciamo un roleplay in italiano: tu sei l\'impiegato della banca e io il cliente. Inizia tu.',
  Scuola:
    'Facciamo un roleplay in italiano: tu sei l\'insegnante e io il genitore a un colloquio. Inizia tu.',
  Spesa:
    'Facciamo un roleplay in italiano: tu sei il cassiere del supermercato e io il cliente. Inizia tu.',
};

export default function ItalianoScreen({ route, navigation }: any) {
  const { profile } = useAuth();
  const livello: string = route?.params?.profileLevel ?? profile?.livello_italiano ?? 'B1';

  const [lesson, setLesson] = useState<LessonData | null>(null);
  const [progress, setProgress] = useState<ItalianProgress>({ punti: 0, streak: 0, esercizi: 0 });
  const [leaderboard, setLeaderboard] = useState<LeaderboardRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [lessonVisible, setLessonVisible] = useState(false);

  const [quiz, setQuiz] = useState<QuizQuestion[]>([]);
  const [quizIndex, setQuizIndex] = useState(0);
  const [answers, setAnswers] = useState<Array<{ id: string; scelta: number }>>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [result, setResult] = useState<QuizResult | null>(null);
  const [quizLoading, setQuizLoading] = useState(false);

  const load = useCallback(async () => {
    try {
      const [lessonResult, progressResult] = await Promise.all([
        apiService.getLesson(livello),
        apiService.getProgress(),
      ]);
      if (lessonResult.data) {
        setLesson(lessonResult.data);
        setProgress(lessonResult.data.progresso);
      }
      if (progressResult.data) {
        setProgress(progressResult.data.mio);
        setLeaderboard(progressResult.data.classifica ?? []);
      }
    } catch {
      // Offline: la schermata resta utilizzabile senza dati remoti.
    } finally {
      setLoading(false);
    }
  }, [livello]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const startQuiz = async () => {
    setQuizLoading(true);
    setResult(null);
    try {
      const response = await apiService.getQuiz(livello, 5);
      const questions = response.data?.domande ?? [];
      if (!questions.length) {
        Alert.alert('Quiz non disponibile', 'Il backend non ha restituito domande. Riprova.');
        return;
      }
      setQuiz(questions);
      setQuizIndex(0);
      setAnswers([]);
      setSelected(null);
    } catch (error: any) {
      Alert.alert('Errore', error?.message ?? 'Impossibile caricare il quiz.');
    } finally {
      setQuizLoading(false);
    }
  };

  const answer = (choice: number) => {
    if (selected !== null) return;
    const question = quiz[quizIndex];
    setSelected(choice);
    setAnswers((previous) => [...previous, { id: question.id, scelta: choice }]);
  };

  const nextQuestion = async () => {
    if (quizIndex + 1 < quiz.length) {
      setQuizIndex((index) => index + 1);
      setSelected(null);
      return;
    }
    setQuizLoading(true);
    try {
      const response = await apiService.submitQuiz(answers, livello);
      if (response.data) {
        setResult(response.data);
        setProgress(response.data.progresso);
        const refreshed = await apiService.getProgress();
        if (refreshed.data) setLeaderboard(refreshed.data.classifica ?? []);
      }
    } catch (error: any) {
      Alert.alert('Errore', error?.message ?? 'Impossibile salvare il punteggio.');
    } finally {
      setQuizLoading(false);
    }
  };

  const closeQuiz = () => {
    setQuiz([]);
    setResult(null);
    setSelected(null);
    setQuizIndex(0);
    setAnswers([]);
  };

  const topTwo = leaderboard.slice(0, 2);

  return (
    <SafeAreaView className="flex-1 bg-[#0a0a0f]">
      <StatusBar style="light" />
      <ScrollView className="flex-1 p-5">
        <View className="flex-row justify-between items-center mb-8">
          <View>
            <Text className="text-4xl font-extrabold text-white">🇮🇹 Italiano</Text>
            <Text className="text-[#06b6d4] text-lg font-bold">Livello Famiglia: {livello}</Text>
            <Text className="text-[#8888a0] text-sm mt-1">
              I tuoi punti: {progress.punti} · serie: {progress.streak} 🔥
            </Text>
          </View>
          <View className="bg-[rgba(255,255,255,0.08)] p-3 rounded-2xl border border-[rgba(255,255,255,0.1)]">
            {topTwo.length ? (
              topTwo.map((row) => (
                <Text key={row.slug} className="text-white text-sm font-bold">
                  {row.nome} 🔥{row.streak}
                </Text>
              ))
            ) : (
              <Text className="text-white text-sm font-bold">Fai il primo quiz!</Text>
            )}
          </View>
        </View>

        <View className="bg-[#1e1b4b] p-6 rounded-[32px] mb-6 border border-[#7c3aed] shadow-lg shadow-[#7c3aed]">
          <View className="bg-[#7c3aed] self-start px-3 py-1 rounded-full mb-4">
            <Text className="text-white font-bold text-xs uppercase tracking-widest">Lezione Quotidiana</Text>
          </View>
          {loading ? (
            <ActivityIndicator color="#a5b4fc" />
          ) : (
            <>
              <Text className="text-white text-3xl font-extrabold mb-2">
                {lesson?.lezione.titolo ?? 'Lezione non disponibile'}
              </Text>
              <Text className="text-[#a5b4fc] text-lg mb-6 leading-6">
                {lesson ? `${lesson.lezione.spiegazione.slice(0, 140)}…` : 'Collega il backend per caricare la lezione.'}
              </Text>
              <TouchableOpacity
                onPress={() => {
                  if (!lesson) {
                    Alert.alert('Lezione non disponibile', 'Controlla la connessione al backend.');
                    return;
                  }
                  setLessonVisible(true);
                }}
                className="bg-white py-4 rounded-2xl items-center shadow-md"
              >
                <Text className="text-[#4c1d95] font-black text-xl">Inizia Lezione (5 min) →</Text>
              </TouchableOpacity>
            </>
          )}
        </View>

        <View className="bg-[#164e63] p-6 rounded-[32px] mb-8 border border-[#06b6d4] shadow-lg">
          <View className="bg-[#06b6d4] self-start px-3 py-1 rounded-full mb-4">
            <Text className="text-white font-bold text-xs uppercase tracking-widest">Sfida Famiglia</Text>
          </View>

          {quizLoading ? (
            <ActivityIndicator color="#cffafe" />
          ) : result ? (
            <View>
              <Text className="text-white text-2xl font-extrabold mb-2">
                Risultato: {result.corrette}/{result.totale}
              </Text>
              <Text className="text-[#cffafe] text-lg mb-2">
                +{result.punteggio} punti · {result.percentuale}%
              </Text>
              {result.dettaglio.slice(0, 2).map((item) => (
                <Text key={item.id} className="text-[#cffafe] text-sm mb-1">
                  {item.corretta ? '✅' : '❌'} {item.spiegazione}
                </Text>
              ))}
              <TouchableOpacity
                onPress={closeQuiz}
                className="bg-transparent py-4 rounded-2xl items-center border-2 border-white mt-4"
              >
                <Text className="text-white font-black text-xl">Chiudi</Text>
              </TouchableOpacity>
            </View>
          ) : quiz.length ? (
            <View>
              <Text className="text-[#cffafe] text-sm mb-2">
                Domanda {quizIndex + 1} di {quiz.length} · livello {quiz[quizIndex].livello}
              </Text>
              <Text className="text-white text-xl font-extrabold mb-4">{quiz[quizIndex].domanda}</Text>
              {quiz[quizIndex].opzioni.map((option, index) => {
                const isSelected = selected === index;
                return (
                  <TouchableOpacity
                    key={`${quiz[quizIndex].id}-${index}`}
                    onPress={() => answer(index)}
                    className={`p-4 rounded-2xl mb-2 border ${
                      isSelected ? 'bg-white border-white' : 'bg-[#0e3a4a] border-[#67e8f9]/40'
                    }`}
                  >
                    <Text className={`font-bold ${isSelected ? 'text-[#164e63]' : 'text-white'}`}>
                      {option}
                    </Text>
                  </TouchableOpacity>
                );
              })}
              <TouchableOpacity
                onPress={nextQuestion}
                disabled={selected === null}
                className={`py-4 rounded-2xl items-center mt-2 border-2 ${
                  selected === null ? 'border-white/30' : 'border-white'
                }`}
              >
                <Text className={`font-black text-lg ${selected === null ? 'text-white/40' : 'text-white'}`}>
                  {quizIndex + 1 < quiz.length ? 'Avanti →' : 'Vedi risultato'}
                </Text>
              </TouchableOpacity>
            </View>
          ) : (
            <>
              <Text className="text-white text-2xl font-extrabold mb-2">Quiz di 60 Secondi ⏱️</Text>
              <Text className="text-[#cffafe] text-lg mb-6">
                Metti alla prova la tua memoria e fai guadagnare 10 punti al tuo profilo!
              </Text>
              <TouchableOpacity
                onPress={startQuiz}
                className="bg-transparent py-4 rounded-2xl items-center border-2 border-white"
              >
                <Text className="text-white font-black text-xl">Gioca Subito</Text>
              </TouchableOpacity>
            </>
          )}
        </View>

        <Text className="text-white text-2xl font-bold mb-5 ml-2">Simula Situazioni Reali</Text>
        <View className="flex-row flex-wrap justify-between">
          {SCENARI.map((item, index) => (
            <TouchableOpacity
              key={index}
              onPress={() =>
                navigation.navigate('Chat', { initialPrompt: SCENARIO_PROMPTS[item.title] })
              }
              className={`w-[48%] p-6 rounded-3xl items-center mb-4 border ${item.color}`}
            >
              <Text className="text-5xl mb-2">{item.icon}</Text>
              <Text className="text-white text-xl font-bold">{item.title}</Text>
            </TouchableOpacity>
          ))}
        </View>
        <View className="h-10" />
      </ScrollView>

      <Modal visible={lessonVisible} animationType="slide" transparent onRequestClose={() => setLessonVisible(false)}>
        <View className="flex-1 bg-black/70 justify-end">
          <View className="bg-[#12121c] rounded-t-[32px] p-6 max-h-[85%]">
            <ScrollView showsVerticalScrollIndicator={false}>
              <Text className="text-[#a5b4fc] text-xs uppercase font-bold tracking-widest mb-2">
                Lezione · {lesson?.lezione.livello}
              </Text>
              <Text className="text-white text-3xl font-extrabold mb-4">
                {lesson?.lezione.titolo}
              </Text>
              <Text className="text-[#e5e7eb] text-lg leading-7 mb-4">{lesson?.lezione.spiegazione}</Text>
              {(lesson?.lezione.esempi ?? []).map((example, index) => (
                <Text key={index} className="text-[#67e8f9] text-base mb-1">
                  • {example}
                </Text>
              ))}
              <View className="bg-[#ffffff10] p-4 rounded-2xl mt-4">
                <Text className="text-white font-bold mb-1">✏️ Esercizio</Text>
                <Text className="text-[#e5e7eb]">{lesson?.lezione.esercizio}</Text>
              </View>
              <TouchableOpacity
                onPress={() => {
                  if (lesson) {
                    setLessonVisible(false);
                    navigation.navigate('Chat', {
                      initialPrompt: `Aiutami con questa lezione di italiano: ${lesson.lezione.titolo}. ${lesson.lezione.esercizio}`,
                    });
                  }
                }}
                className="bg-[#7c3aed] py-4 rounded-2xl items-center mt-5"
              >
                <Text className="text-white font-black text-lg">Chiedi aiuto ad ATLAS</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={() => setLessonVisible(false)}
                className="py-4 items-center mt-1"
              >
                <Text className="text-[#8888a0]">Chiudi</Text>
              </TouchableOpacity>
            </ScrollView>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}
