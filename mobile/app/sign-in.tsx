import { useRouter } from 'expo-router';
import * as AppleAuthentication from 'expo-apple-authentication';
import { useEffect, useMemo, useReducer, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useAuth } from '../src/features/auth/AuthProvider';
import { dogfoodRuntimeEnabled } from '../src/config/environment';
import {
  createInitialOnboardingState,
  onboardingReducer,
} from '../src/features/onboarding/onboardingReducer';
import {
  AppleAuthFlowError,
  createNativeAppleAuthorizationAdapter,
  getAppleDeviceMetadata,
  runAppleSignIn,
  type AppleAuthorizationAdapter,
} from '../src/integrations/apple/appleAuthAdapter';
import { colors } from '../src/theme/colors';
import { radius } from '../src/theme/radius';
import { spacing } from '../src/theme/spacing';
import { typography } from '../src/theme/typography';

export default function SignInRoute() {
  const router = useRouter();
  const {
    state: authState,
    createAppleChallenge,
    signInWithApple,
  } = useAuth();
  const [flow, dispatch] = useReducer(
    onboardingReducer,
    undefined,
    createInitialOnboardingState,
  );
  const [supported, setSupported] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const adapterRef = useRef<AppleAuthorizationAdapter | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (flow.step !== 'apple_sign_in') return;
    let active = true;
    void createNativeAppleAuthorizationAdapter()
      .then(async (adapter) => {
        adapterRef.current = adapter;
        const available = await adapter.isSupported();
        if (active) setSupported(available);
      })
      .catch(() => {
        if (active) setSupported(false);
      });
    return () => {
      active = false;
    };
  }, [flow.step]);

  const errorCopy = useMemo(() => {
    if (message) return message;
    if (authState.status === 'expired' && authState.error) return authState.error;
    if (authState.status === 'revoked') {
      return 'Сессия завершена. Войдите снова через Apple.';
    }
    return null;
  }, [authState.error, authState.status, message]);

  const authorize = async () => {
    if (busy || !adapterRef.current) return;
    setBusy(true);
    setMessage(null);
    try {
      const device = await getAppleDeviceMetadata();
      await runAppleSignIn({
        device,
        native: adapterRef.current,
        createChallenge: createAppleChallenge,
        exchange: signInWithApple,
      });
      if (!mountedRef.current) return;
      dispatch({ type: 'auth/succeeded' });
    } catch (error: unknown) {
      if (!mountedRef.current) return;
      if (error instanceof AppleAuthFlowError) {
        if (error.reason === 'cancelled') {
          setMessage('Вход отменён. Данные не изменились.');
        } else if (error.reason === 'unsupported') {
          setSupported(false);
        } else {
          setMessage('Не удалось войти через Apple. Попробуйте ещё раз.');
        }
      } else {
        setMessage('Не удалось войти через Apple. Проверьте соединение.');
      }
    } finally {
      if (mountedRef.current) setBusy(false);
    }
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
      >
        <View accessibilityElementsHidden style={styles.pathMark}>
          <View style={styles.pathLine} />
          <View style={styles.pathDot} />
        </View>

        {flow.step === 'welcome' ? (
          <View style={styles.stage}>
            <Text style={styles.eyebrow}>AI Life Planner</Text>
            <Text accessibilityRole="header" style={styles.title}>
              Твоя цель уже расписана на сегодня
            </Text>
            <Text style={styles.lead}>
              Расскажи, как живёшь сейчас и кем хочешь стать. Мы соберём
              реалистичный путь и встроим его в твой день.
            </Text>
            <View style={styles.promiseList}>
              <PromiseLine text="Один рассказ вместо длинной анкеты" />
              <PromiseLine text="До трёх активных направлений" />
              <PromiseLine text="Резерв времени, чтобы план оставался живым" />
            </View>
            <Pressable
              accessibilityRole="button"
              onPress={() => dispatch({ type: 'welcome/continued' })}
              style={({ pressed }) => [
                styles.primaryButton,
                pressed && styles.pressed,
              ]}
            >
              <Text style={styles.primaryButtonText}>Продолжить</Text>
            </Pressable>
          </View>
        ) : (
          <View style={styles.stage}>
            <Pressable
              accessibilityLabel="Назад"
              accessibilityRole="button"
              onPress={() => dispatch({ type: 'navigation/back' })}
              style={styles.backButton}
            >
              <Text style={styles.backText}>‹</Text>
            </Pressable>
            <Text style={styles.eyebrow}>Сохранить путь</Text>
            <Text accessibilityRole="header" style={styles.title}>
              Войти через Apple
            </Text>
            <Text style={styles.lead}>
              Вход привяжет планы к вашему аккаунту и позволит безопасно
              продолжить на этом iPhone.
            </Text>

            <View style={styles.appleArea}>
              {supported === null ? (
                <View accessible accessibilityLabel="Проверяю вход через Apple" style={styles.checking}>
                  <ActivityIndicator color={colors.burgundy} />
                  <Text style={styles.checkingText}>Проверяю Apple-вход…</Text>
                </View>
              ) : supported && Platform.OS === 'ios' ? (
                <View
                  accessibilityState={{ busy, disabled: busy }}
                  pointerEvents={busy ? 'none' : 'auto'}
                  style={busy ? styles.busy : undefined}
                >
                  <AppleAuthentication.AppleAuthenticationButton
                    buttonStyle={
                      AppleAuthentication.AppleAuthenticationButtonStyle.BLACK
                    }
                    buttonType={
                      AppleAuthentication.AppleAuthenticationButtonType.CONTINUE
                    }
                    cornerRadius={radius.control}
                    onPress={() => void authorize()}
                    style={styles.appleButton}
                  />
                </View>
              ) : (
                <View style={styles.unsupported}>
                  <Text style={styles.unsupportedTitle}>
                    Apple-вход доступен в iOS development build
                  </Text>
                  <Text style={styles.unsupportedCopy}>
                    Здесь можно проверить текстовый onboarding. Отправка и
                    сохранение плана останутся выключенными — фиктивного входа
                    не будет.
                  </Text>
                  <Pressable
                    accessibilityRole="button"
                    onPress={() => router.push('/onboarding?textOnly=1')}
                    style={({ pressed }) => [
                      styles.secondaryButton,
                      pressed && styles.pressed,
                    ]}
                  >
                    <Text style={styles.secondaryButtonText}>
                      Открыть текстовый режим
                    </Text>
                  </Pressable>
                  {dogfoodRuntimeEnabled ? (
                    <Pressable
                      accessibilityRole="button"
                      onPress={() => router.push('/setup')}
                      style={({ pressed }) => [
                        styles.secondaryButton,
                        pressed && styles.pressed,
                      ]}
                    >
                      <Text style={styles.secondaryButtonText}>
                        Подключить локальный dogfood
                      </Text>
                    </Pressable>
                  ) : null}
                </View>
              )}
            </View>

            {errorCopy ? (
              <Text accessibilityLiveRegion="polite" style={styles.error}>
                {errorCopy}
              </Text>
            ) : null}
            <Text style={styles.privacy}>
              Токен Apple не сохраняется в журнале и не показывается в
              интерфейсе. Сессия хранится в iOS Keychain.
            </Text>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function PromiseLine({ text }: { text: string }) {
  return (
    <View style={styles.promiseLine}>
      <View accessibilityElementsHidden style={styles.promiseDot} />
      <Text style={styles.promiseText}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: colors.paper },
  content: {
    flexGrow: 1,
    paddingHorizontal: spacing.screen,
    paddingTop: spacing.lg,
    paddingBottom: spacing.xl,
  },
  pathMark: {
    width: 22,
    height: 88,
    alignItems: 'center',
    marginBottom: spacing.xl,
  },
  pathLine: { flex: 1, width: 2, backgroundColor: colors.burgundy },
  pathDot: {
    width: 10,
    height: 10,
    borderRadius: radius.round,
    backgroundColor: colors.burgundy,
  },
  stage: { flex: 1 },
  eyebrow: {
    ...typography.caption,
    color: colors.burgundy,
    letterSpacing: 0.6,
    textTransform: 'uppercase',
  },
  title: {
    ...typography.screenTitle,
    color: colors.ink,
    marginTop: spacing.sm,
    maxWidth: 340,
  },
  lead: {
    ...typography.body,
    color: colors.muted,
    marginTop: spacing.md,
    maxWidth: 350,
  },
  promiseList: {
    marginTop: 40,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.rule,
  },
  promiseLine: {
    minHeight: 54,
    flexDirection: 'row',
    alignItems: 'center',
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.rule,
  },
  promiseDot: {
    width: 6,
    height: 6,
    marginRight: spacing.sm,
    borderRadius: radius.round,
    backgroundColor: colors.burgundy,
  },
  promiseText: { ...typography.body, flex: 1, color: colors.ink },
  primaryButton: {
    minHeight: 52,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 'auto',
    paddingHorizontal: spacing.md,
    borderRadius: radius.control,
    backgroundColor: colors.ink,
  },
  primaryButtonText: { ...typography.bodyMedium, color: colors.paper },
  backButton: {
    width: spacing.touch,
    height: spacing.touch,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.lg,
    marginLeft: -spacing.sm,
  },
  backText: { fontSize: 34, lineHeight: 38, color: colors.ink },
  appleArea: { marginTop: 40 },
  appleButton: { width: '100%', height: 52 },
  checking: {
    minHeight: 52,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkingText: { ...typography.body, color: colors.muted, marginLeft: spacing.sm },
  unsupported: {
    paddingVertical: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: colors.rule,
  },
  unsupportedTitle: { ...typography.bodyMedium, color: colors.ink },
  unsupportedCopy: { ...typography.body, color: colors.muted, marginTop: spacing.xs },
  secondaryButton: {
    minHeight: spacing.touch,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: spacing.md,
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: radius.control,
  },
  secondaryButtonText: { ...typography.bodyMedium, color: colors.ink },
  error: { ...typography.body, color: colors.burgundy, marginTop: spacing.md },
  privacy: {
    ...typography.caption,
    color: colors.muted,
    marginTop: 'auto',
    paddingTop: spacing.xl,
  },
  busy: { opacity: 0.5 },
  pressed: { opacity: 0.72 },
});
