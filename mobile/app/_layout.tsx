import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { PlannerProvider } from '../src/features/planner/PlannerProvider';
import { AppRouteGate } from '../src/features/auth/AppRouteGate';
import { AuthProvider } from '../src/features/auth/AuthProvider';
import { colors } from '../src/theme/colors';

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <AuthProvider>
        <PlannerProvider>
          <StatusBar style="dark" backgroundColor={colors.paper} />
          <Stack
            screenOptions={{
              headerShown: false,
              contentStyle: { backgroundColor: colors.paper },
              animation: 'slide_from_right',
            }}
          >
            <Stack.Screen name="(tabs)" />
            <Stack.Screen name="sign-in" />
            <Stack.Screen name="onboarding" />
            <Stack.Screen name="onboarding-preview" />
            <Stack.Screen name="task/[id]" />
            <Stack.Screen name="goal/[id]" />
            <Stack.Screen name="setup" options={{ presentation: 'modal' }} />
          </Stack>
          <AppRouteGate />
        </PlannerProvider>
      </AuthProvider>
    </SafeAreaProvider>
  );
}
