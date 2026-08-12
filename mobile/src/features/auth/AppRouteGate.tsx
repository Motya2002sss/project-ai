import type { Href } from 'expo-router';
import { useRouter, useSegments } from 'expo-router';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { ApiClient } from '../../api/client';
import {
  apiBaseUrl,
  dogfoodRuntimeEnabled,
} from '../../config/environment';
import { getDogfoodToken } from '../../storage/mobileStorage';
import { colors } from '../../theme/colors';
import { spacing } from '../../theme/spacing';
import { typography } from '../../theme/typography';
import { OnboardingApi } from '../onboarding/onboardingApi';
import {
  appAreaFromSegment,
  decideAppGate,
  subscribeDogfoodAccessChanges,
  shouldRevalidateOnboarding,
  type DogfoodAccess,
  type GateOnboardingStatus,
} from './appGate';
import { useAuth } from './AuthProvider';

export function AppRouteGate() {
  const router = useRouter();
  const segments = useSegments();
  const {
    state: authState,
    getAccessToken,
    recoverAuthentication,
  } = useAuth();
  const [dogfoodAccess, setDogfoodAccess] =
    useState<DogfoodAccess>('checking');
  const [dogfoodCheckVersion, setDogfoodCheckVersion] = useState(0);
  const [onboardingStatus, setOnboardingStatus] =
    useState<GateOnboardingStatus>('unknown');
  const [retryVersion, setRetryVersion] = useState(0);
  const currentArea = appAreaFromSegment(segments[0]);
  const previousAreaRef = useRef(currentArea);
  const routeNeedsOnboardingRevalidation = shouldRevalidateOnboarding(
    previousAreaRef.current,
    currentArea,
  );

  const onboardingApi = useMemo(
    () =>
      new OnboardingApi(
        new ApiClient({
          baseUrl: apiBaseUrl,
          tokenProvider: getAccessToken,
          recoverAuthentication,
        }),
      ),
    [getAccessToken, recoverAuthentication],
  );

  useEffect(
    () =>
      subscribeDogfoodAccessChanges(dogfoodRuntimeEnabled, () => {
        setDogfoodAccess('allowed');
        setDogfoodCheckVersion((version) => version + 1);
      }),
    [],
  );

  useEffect(() => {
    if (authState.status === 'authenticated') {
      setDogfoodAccess('denied');
      return;
    }
    if (
      authState.status === 'hydrating' ||
      authState.status === 'refreshing'
    ) {
      setDogfoodAccess('checking');
      return;
    }
    if (!dogfoodRuntimeEnabled) {
      setDogfoodAccess('denied');
      return;
    }
    let active = true;
    setDogfoodAccess('checking');
    void getDogfoodToken()
      .then((token) => {
        if (active) setDogfoodAccess(token ? 'allowed' : 'denied');
      })
      .catch(() => {
        if (active) setDogfoodAccess('denied');
      });
    return () => {
      active = false;
    };
  }, [authState.status, dogfoodCheckVersion]);

  useEffect(() => {
    if (authState.status !== 'authenticated' || !authState.user) {
      setOnboardingStatus('unknown');
      return;
    }
    let active = true;
    setOnboardingStatus('checking');
    void onboardingApi
      .getState()
      .then((state) => {
        if (active) setOnboardingStatus(state.status);
      })
      .catch(() => {
        if (active) setOnboardingStatus('failed');
      });
    return () => {
      active = false;
    };
  }, [
    authState.status,
    authState.user,
    onboardingApi,
    currentArea,
    retryVersion,
  ]);

  useEffect(() => {
    previousAreaRef.current = currentArea;
  }, [currentArea]);

  const decision = decideAppGate({
    authStatus: authState.status,
    currentArea,
    dogfoodAccess,
    dogfoodRuntimeEnabled,
    offlineIdentityAvailable:
      authState.status === 'expired' && authState.user !== null,
    onboardingStatus: routeNeedsOnboardingRevalidation
      ? 'checking'
      : onboardingStatus,
  });

  useEffect(() => {
    if (decision.kind === 'redirect') {
      router.replace(decision.href as Href);
    }
  }, [decision, router]);

  if (decision.kind === 'allow') return null;

  return (
    <View
      accessibilityLabel={
        decision.kind === 'blocked'
          ? 'Не удалось проверить onboarding'
          : 'Проверяю доступ к приложению'
      }
      accessibilityViewIsModal
      style={styles.cover}
    >
      {decision.kind === 'blocked' ? (
        <View style={styles.message}>
          <Text accessibilityRole="header" style={styles.title}>
            Не удалось проверить настройку
          </Text>
          <Text style={styles.body}>
            Данные на устройстве сохранены. Проверьте соединение и повторите.
          </Text>
          <Pressable
            accessibilityRole="button"
            onPress={() => setRetryVersion((value) => value + 1)}
            style={({ pressed }) => [
              styles.retry,
              pressed && styles.retryPressed,
            ]}
          >
            <Text style={styles.retryText}>Повторить</Text>
          </Pressable>
        </View>
      ) : (
        <ActivityIndicator accessibilityLabel="Загрузка" color={colors.burgundy} />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  cover: {
    ...StyleSheet.absoluteFillObject,
    zIndex: 100,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.screen,
    backgroundColor: colors.paper,
  },
  message: { width: '100%', maxWidth: 420, alignItems: 'flex-start' },
  title: { ...typography.screenTitle, color: colors.ink },
  body: { ...typography.body, color: colors.muted, marginTop: spacing.sm },
  retry: {
    minHeight: 48,
    justifyContent: 'center',
    marginTop: spacing.lg,
    paddingHorizontal: spacing.lg,
    backgroundColor: colors.burgundy,
  },
  retryPressed: { opacity: 0.82 },
  retryText: { ...typography.bodyMedium, color: colors.paper },
});
