import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { ActivityIndicator, AppState, Text, View } from 'react-native';
import { NativeWindStyleSheet } from 'nativewind';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import AsyncStorage from '@react-native-async-storage/async-storage';
import ProfileScreen from './src/screens/ProfileScreen';
import HomeScreen from './src/screens/HomeScreen';
import ChatScreen from './src/screens/ChatScreen';
import ListaSpesaScreen from './src/screens/ListaSpesaScreen';
import ItalianoScreen from './src/screens/ItalianoScreen';
import BudgetScreen from './src/screens/BudgetScreen';
import IntegrationsScreen from './src/screens/IntegrationsScreen';
import PdfScreen from './src/screens/PdfScreen';
import CONFIG from './src/config';
import apiService, { ApiError } from './src/services/api';
import {
  configureNotifications,
  registerPushToken,
  syncLocalRemindersFromSettings,
  syncUpcomingReminders,
  unregisterPushToken,
  cancelLocalReminders,
  cancelUpcomingReminderNotifications,
} from './src/services/notifications';

// Expo web non carica il foglio CSS generato da NativeWind: usa gli stili
// nativi inline anche nel browser, così la resa resta identica alle app mobile.
NativeWindStyleSheet.setOutput({ default: 'native' });

const Stack = createNativeStackNavigator();
const Tab = createBottomTabNavigator();

export interface ProfileInfo {
  slug: string;
  nome: string;
  lingua_madre: string;
  livello_italiano: string;
}

export interface AuthContextValue {
  authToken: string | null;
  profileId: string | null;
  profile: ProfileInfo | null;
  ready: boolean;
  setAuth: (token: string | null, profileId: string | null) => Promise<void>;
  clearAuth: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  authToken: null,
  profileId: null,
  profile: null,
  ready: false,
  setAuth: async () => {},
  clearAuth: async () => {},
});

export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}

function TabIcon({ icon, focused }: { icon: string; focused: boolean }) {
  return (
    <View style={{ opacity: focused ? 1 : 0.5 }}>
      <Text style={{ fontSize: 22 }}>{icon}</Text>
    </View>
  );
}

function MainTabs() {
  // Il profilo arriva dal contesto di autenticazione: funziona anche quando la
  // sessione viene ripristinata all'avvio senza parametri di navigazione.
  const { profileId, profile } = useAuth();

  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: '#0a0a0f',
          borderTopColor: '#ffffff10',
          borderTopWidth: 1,
          height: 70,
          paddingBottom: 12,
          paddingTop: 8,
        },
        tabBarActiveTintColor: '#7c3aed',
        tabBarInactiveTintColor: '#8888a0',
        tabBarLabelStyle: { fontSize: 12, fontWeight: '700' },
      }}
    >
      <Tab.Screen
        name="Home"
        component={HomeScreen}
        initialParams={{ profileId }}
        options={{
          tabBarIcon: ({ focused }) => <TabIcon icon="🏠" focused={focused} />,
          tabBarLabel: 'Home',
        }}
      />
      <Tab.Screen
        name="Chat"
        component={ChatScreen}
        initialParams={{ profileId }}
        options={{
          tabBarIcon: ({ focused }) => <TabIcon icon="💬" focused={focused} />,
          tabBarLabel: 'Chat',
        }}
      />
      <Tab.Screen
        name="Italiano"
        component={ItalianoScreen}
        initialParams={{ profileLevel: profile?.livello_italiano ?? 'B1' }}
        options={{
          tabBarIcon: ({ focused }) => <TabIcon icon="🇮🇹" focused={focused} />,
          tabBarLabel: 'Italiano',
        }}
      />
      <Tab.Screen
        name="Budget"
        component={BudgetScreen}
        initialParams={{ profileId }}
        options={{
          tabBarIcon: ({ focused }) => <TabIcon icon="💰" focused={focused} />,
          tabBarLabel: 'Budget',
        }}
      />
      <Tab.Screen
        name="Impostazioni"
        component={IntegrationsScreen}
        options={{
          tabBarIcon: ({ focused }) => <TabIcon icon="⚙️" focused={focused} />,
          tabBarLabel: 'Impostazioni',
        }}
      />
    </Tab.Navigator>
  );
}

async function loadProfileInfo(slug: string, token: string): Promise<ProfileInfo | null> {
  try {
    const me = await apiService.me(token);
    return {
      slug: me.slug,
      nome: me.nome,
      lingua_madre: me.lingua_madre,
      livello_italiano: me.livello_italiano,
    };
  } catch (error) {
    // Token scaduto/revocato: il chiamante deve riportare l'utente al login.
    if (error instanceof ApiError && error.status === 401) {
      throw error;
    }
    // Offline: usiamo l'ultima info salvata, se disponibile.
    try {
      const raw = await AsyncStorage.getItem(CONFIG.STORAGE_PROFILE_INFO_KEY);
      if (raw) {
        const cached = JSON.parse(raw) as ProfileInfo;
        if (cached?.slug === slug) return cached;
      }
    } catch {
      // nessuna cache
    }
    return null;
  }
}

export default function App() {
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [profile, setProfile] = useState<ProfileInfo | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    configureNotifications();
  }, []);

  // Ripristino sessione: il token viene validato dal backend prima di entrare.
  useEffect(() => {
    (async () => {
      try {
        const [storedToken, storedProfile] = await Promise.all([
          AsyncStorage.getItem(CONFIG.STORAGE_AUTH_TOKEN_KEY),
          AsyncStorage.getItem(CONFIG.STORAGE_PROFILE_KEY),
        ]);
        if (!storedToken || !storedProfile) {
          return;
        }
        const info = await loadProfileInfo(storedProfile, storedToken);
        setAuthToken(storedToken);
        setProfileId(storedProfile);
        setProfile(
          info ?? {
            slug: storedProfile,
            nome: storedProfile,
            lingua_madre: 'Italiano',
            livello_italiano: 'B1',
          }
        );
        // Sessione ripristinata: riallinea subito notifiche e promemoria,
        // senza aspettare che l'utente apra la chat.
        registerPushToken(storedProfile).catch(() => {});
        syncLocalRemindersFromSettings().catch(() => {});
        syncUpcomingReminders().catch(() => {});
      } catch (error) {
        // Token non più valido: puliamo la sessione salvata e mostriamo i profili.
        if (error instanceof ApiError && error.status === 401) {
          await AsyncStorage.multiRemove([
            CONFIG.STORAGE_AUTH_TOKEN_KEY,
            CONFIG.STORAGE_PROFILE_KEY,
            CONFIG.STORAGE_PROFILE_INFO_KEY,
          ]).catch(() => {});
        }
      } finally {
        setReady(true);
      }
    })();
  }, []);

  const persistProfile = async (slug: string, token: string) => {
    const info = await loadProfileInfo(slug, token);
    setProfile(info);
    if (info) {
      await AsyncStorage.setItem(CONFIG.STORAGE_PROFILE_INFO_KEY, JSON.stringify(info));
    }
    // Notifiche: push remote (se configurate) + promemoria locali secondo le impostazioni.
    registerPushToken(slug).catch(() => {});
    syncLocalRemindersFromSettings().catch(() => {});
    syncUpcomingReminders().catch(() => {});
  };

  const setAuth = useCallback(async (token: string | null, slug: string | null) => {
    const tasks: Promise<unknown>[] = [];
    if (token) tasks.push(AsyncStorage.setItem(CONFIG.STORAGE_AUTH_TOKEN_KEY, token));
    else tasks.push(AsyncStorage.removeItem(CONFIG.STORAGE_AUTH_TOKEN_KEY));
    if (slug) tasks.push(AsyncStorage.setItem(CONFIG.STORAGE_PROFILE_KEY, slug));
    else tasks.push(AsyncStorage.removeItem(CONFIG.STORAGE_PROFILE_KEY));
    await Promise.all(tasks);

    // Aggiorna lo stato solo dopo aver salvato il token: la Home monta subito
    // e le sue richieste devono trovarlo già in AsyncStorage.
    setAuthToken(token);
    setProfileId(slug);

    if (token && slug) {
      await persistProfile(slug, token);
    }
  }, []);

  const clearAuth = useCallback(async () => {
    // Revoca la sessione e disattiva il push PRIMA di cancellare le credenziali:
    // le richieste HTTP leggono il token da AsyncStorage.
    try {
      await apiService.logout();
    } catch {
      // Offline: il token scadrà comunque.
    }
    await unregisterPushToken();
    await cancelLocalReminders();
    await cancelUpcomingReminderNotifications();

    setAuthToken(null);
    setProfileId(null);
    setProfile(null);
    await AsyncStorage.multiRemove([
      CONFIG.STORAGE_AUTH_TOKEN_KEY,
      CONFIG.STORAGE_PROFILE_KEY,
      CONFIG.STORAGE_PROFILE_INFO_KEY,
    ]);
  }, []);

  // Sessione scaduta durante l'uso: si torna automaticamente ai profili.
  useEffect(() => {
    apiService.setUnauthorizedHandler(() => {
      clearAuth().catch(() => {});
    });
    return () => apiService.setUnauthorizedHandler(null);
  }, [clearAuth]);

  // Al ritorno in foreground riallineiamo i promemoria: se uno è stato creato
  // da un altro dispositivo o è cambiata la lista, il telefono si aggiorna.
  useEffect(() => {
    const subscription = AppState.addEventListener('change', (state) => {
      if (state === 'active' && authToken) {
        syncUpcomingReminders().catch(() => {});
      }
    });
    return () => subscription.remove();
  }, [authToken]);

  const authenticated = Boolean(authToken && profileId);

  return (
    <AuthContext.Provider
      value={{ authToken, profileId, profile, ready, setAuth, clearAuth }}
    >
      <NavigationContainer>
        {!ready ? (
          <View style={{ flex: 1, backgroundColor: '#0a0a0f', alignItems: 'center', justifyContent: 'center' }}>
            <ActivityIndicator color="#7c3aed" size="large" />
            <Text style={{ color: '#8888a0', marginTop: 16, fontWeight: '700' }}>ATLAS AI</Text>
          </View>
        ) : (
          <Stack.Navigator screenOptions={{ headerShown: false }}>
            {authenticated ? (
              <>
                <Stack.Screen name="Main" component={MainTabs} />
                <Stack.Screen name="ListaSpesa" component={ListaSpesaScreen} />
                <Stack.Screen name="DocumentoPdf" component={PdfScreen} />
              </>
            ) : (
              <Stack.Screen name="Profile" component={ProfileScreen} />
            )}
          </Stack.Navigator>
        )}
      </NavigationContainer>
    </AuthContext.Provider>
  );
}
