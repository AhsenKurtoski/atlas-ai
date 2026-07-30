import React, { createContext, useContext, useEffect, useState } from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Text, View } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import ProfileScreen from './src/screens/ProfileScreen';
import HomeScreen from './src/screens/HomeScreen';
import ChatScreen from './src/screens/ChatScreen';
import ItalianoScreen from './src/screens/ItalianoScreen';
import BudgetScreen from './src/screens/BudgetScreen';
import IntegrationsScreen from './src/screens/IntegrationsScreen';
import CONFIG from './src/config';

const Stack = createNativeStackNavigator();
const Tab = createBottomTabNavigator();

export interface AuthContextValue {
  authToken: string | null;
  profileId: string | null;
  setAuth: (token: string | null, profileId: string | null) => Promise<void>;
  clearAuth: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  authToken: null,
  profileId: null,
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

function MainTabs({ route }: any) {
  const { profileId } = route.params;

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
        initialParams={{ profileLevel: profileId === 'papa' ? 'A2' : 'B1' }}
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

export default function App() {
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [t, p] = await Promise.all([
          AsyncStorage.getItem(CONFIG.STORAGE_AUTH_TOKEN_KEY),
          AsyncStorage.getItem(CONFIG.STORAGE_PROFILE_KEY),
        ]);
        setAuthToken(t);
        setProfileId(p);
      } finally {
        setReady(true);
      }
    })();
  }, []);

  const setAuth = async (token: string | null, profile: string | null) => {
    setAuthToken(token);
    setProfileId(profile);
    const tasks: Promise<void>[] = [];
    if (token) tasks.push(AsyncStorage.setItem(CONFIG.STORAGE_AUTH_TOKEN_KEY, token));
    else tasks.push(AsyncStorage.removeItem(CONFIG.STORAGE_AUTH_TOKEN_KEY));
    if (profile) tasks.push(AsyncStorage.setItem(CONFIG.STORAGE_PROFILE_KEY, profile));
    else tasks.push(AsyncStorage.removeItem(CONFIG.STORAGE_PROFILE_KEY));
    await Promise.all(tasks);
  };

  const clearAuth = async () => {
    setAuthToken(null);
    setProfileId(null);
    await AsyncStorage.multiRemove([CONFIG.STORAGE_AUTH_TOKEN_KEY, CONFIG.STORAGE_PROFILE_KEY]);
  };

  return (
    <AuthContext.Provider value={{ authToken, profileId, setAuth, clearAuth }}>
      <NavigationContainer>
        <Stack.Navigator screenOptions={{ headerShown: false }}>
          <Stack.Screen name="Profile" component={ProfileScreen} />
          <Stack.Screen name="Main" component={MainTabs} />
        </Stack.Navigator>
      </NavigationContainer>
    </AuthContext.Provider>
  );
}
