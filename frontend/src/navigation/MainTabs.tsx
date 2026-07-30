import React from 'react';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import ChatScreen from '../screens/ChatScreen';
import ItalianoScreen from '../screens/ItalianoScreen';
import IntegrationsScreen from '../screens/IntegrationsScreen';
import { Text } from 'react-native';

const Tab = createBottomTabNavigator();

export default function MainTabs({ route }: any) {
  const { profileId } = route.params;

  return (
    <Tab.Navigator 
      screenOptions={{ 
        headerShown: false,
        tabBarStyle: { 
            backgroundColor: '#0a0a0f', 
            borderTopColor: 'rgba(255,255,255,0.1)',
            height: 70,
            paddingBottom: 15
        },
        tabBarActiveTintColor: '#7c3aed',
        tabBarInactiveTintColor: '#8888a0',
        tabBarLabelStyle: { fontSize: 14, fontWeight: 'bold' }
      }}
    >
      <Tab.Screen 
        name="Chat" 
        component={ChatScreen} 
        initialParams={{ profileId }} 
        options={{ tabBarIcon: ({color}) => <Text style={{color, fontSize: 24}}>💬</Text> }}
      />
      
      {/* Mostra il tab Italiano specialmente se è Mamma o Papà */}
      <Tab.Screen 
        name="Italiano" 
        component={ItalianoScreen} 
        initialParams={{ profileLevel: profileId === 'papa' ? 'A2' : 'B1' }} 
        options={{ tabBarIcon: ({color}) => <Text style={{color, fontSize: 24}}>📚</Text> }}
      />

      <Tab.Screen 
        name="Impostazioni" 
        component={IntegrationsScreen} 
        options={{ tabBarIcon: ({color}) => <Text style={{color, fontSize: 24}}>⚙️</Text> }}
      />
    </Tab.Navigator>
  );
}
