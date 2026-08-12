import { Redirect, useRouter } from 'expo-router';
import { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';

import { usePlanner } from '../src/features/planner/PlannerProvider';
import { dogfoodRuntimeEnabled } from '../src/config/environment';
import { notifyDogfoodAccessChanged } from '../src/features/auth/appGate';
import { colors } from '../src/theme/colors';
import { radius } from '../src/theme/radius';
import { spacing } from '../src/theme/spacing';
import { typography } from '../src/theme/typography';

export default function SetupRoute() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { apiBaseUrl, updateDogfoodToken } = usePlanner();
  const [token, setToken] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!dogfoodRuntimeEnabled) return <Redirect href="/sign-in" />;

  const save = async () => {
    if (!token.trim() || !apiBaseUrl || saving) return;
    setSaving(true);
    setError(null);
    try {
      await updateDogfoodToken(token);
      notifyDogfoodAccessChanged(dogfoodRuntimeEnabled);
      router.replace('/');
    } catch {
      setError('Не удалось сохранить доступ. Повторите.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.keyboard}
      >
        <View style={styles.topBar}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Закрыть"
            onPress={() =>
              router.canGoBack() ? router.back() : router.replace('/')
            }
            style={styles.close}
          >
            <Text style={styles.closeText}>×</Text>
          </Pressable>
        </View>
        <View style={styles.content}>
          <Text style={styles.eyebrow}>Только development</Text>
          <Text accessibilityRole="header" style={styles.title}>
            Подключить backend
          </Text>
          <Text style={styles.copy}>
            Base URL задаётся через `.env.local`. Bearer token сохранится в iOS
            Keychain и не попадёт в repository.
          </Text>
          <View style={styles.configLine}>
            <Text style={styles.configLabel}>Backend</Text>
            <Text selectable style={styles.configValue}>
              {apiBaseUrl || 'EXPO_PUBLIC_API_BASE_URL не задан'}
            </Text>
          </View>
          <TextInput
            accessibilityLabel="Dogfood bearer token"
            autoCapitalize="none"
            autoCorrect={false}
            onChangeText={setToken}
            placeholder="MOBILE_DOGFOOD_TOKEN"
            placeholderTextColor={colors.muted}
            secureTextEntry
            style={styles.input}
            value={token}
          />
          {error ? (
            <Text accessibilityLiveRegion="polite" style={styles.error}>
              {error}
            </Text>
          ) : null}
        </View>
        <View style={[styles.bottom, { paddingBottom: Math.max(insets.bottom, 16) }]}>
          <Pressable
            accessibilityRole="button"
            accessibilityState={{
              disabled: !token.trim() || !apiBaseUrl || saving,
              busy: saving,
            }}
            disabled={!token.trim() || !apiBaseUrl || saving}
            onPress={() => void save()}
            style={[
              styles.save,
              (!token.trim() || !apiBaseUrl || saving) && styles.disabled,
            ]}
          >
            <Text style={styles.saveText}>{saving ? 'Сохраняю…' : 'Подключить'}</Text>
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: colors.paper },
  keyboard: { flex: 1 },
  topBar: { alignItems: 'flex-end', paddingHorizontal: spacing.screen },
  close: {
    width: spacing.touch,
    height: spacing.touch,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: radius.control,
  },
  closeText: { fontSize: 24, lineHeight: 26, color: colors.muted },
  content: { flex: 1, padding: spacing.screen, paddingTop: 42 },
  eyebrow: {
    ...typography.caption,
    color: colors.burgundy,
    textTransform: 'uppercase',
    letterSpacing: 0.4,
  },
  title: { ...typography.detailTitle, color: colors.ink, marginTop: spacing.xs },
  copy: { ...typography.body, color: colors.muted, marginTop: spacing.md },
  configLine: {
    marginTop: spacing.xl,
    paddingVertical: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: colors.rule,
  },
  configLabel: { ...typography.caption, color: colors.muted },
  configValue: { ...typography.body, color: colors.ink, marginTop: spacing.xxs },
  input: {
    minHeight: 52,
    marginTop: spacing.lg,
    paddingHorizontal: spacing.sm,
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: radius.input,
    backgroundColor: colors.raised,
    color: colors.ink,
    ...typography.body,
  },
  bottom: {
    paddingTop: spacing.sm,
    paddingHorizontal: spacing.screen,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.rule,
  },
  save: {
    minHeight: 52,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.control,
    backgroundColor: colors.ink,
  },
  saveText: { ...typography.bodyMedium, color: colors.paper },
  disabled: { opacity: 0.4 },
  error: { ...typography.body, color: colors.burgundy, marginTop: spacing.sm },
});
