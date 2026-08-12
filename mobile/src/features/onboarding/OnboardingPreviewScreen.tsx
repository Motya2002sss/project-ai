import AsyncStorage from '@react-native-async-storage/async-storage';
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';

import { ApiClient } from '../../api/client';
import { ApiError } from '../../api/errors';
import { apiBaseUrl } from '../../config/environment';
import { colors } from '../../theme/colors';
import { radius } from '../../theme/radius';
import { spacing } from '../../theme/spacing';
import { typography } from '../../theme/typography';
import { useAuth } from '../auth/AuthProvider';
import { OnboardingApi } from './onboardingApi';
import { OnboardingDraftStore } from './onboardingDraftStorage';
import {
  createInitialOnboardingState,
  onboardingReducer,
  type GoalAllocation,
  type OnboardingPreview,
} from './onboardingReducer';

interface OnboardingPreviewScreenProps {
  onComplete: () => void;
  onEdit: () => void;
  onRequireSignIn: () => void;
}

const dayNames: Record<number, string> = {
  1: 'пн',
  2: 'вт',
  3: 'ср',
  4: 'чт',
  5: 'пт',
  6: 'сб',
  7: 'вс',
};

export function OnboardingPreviewScreen({
  onComplete,
  onEdit,
  onRequireSignIn,
}: OnboardingPreviewScreenProps) {
  const { width } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const { state: authState, getAccessToken, recoverAuthentication } = useAuth();
  const [state, dispatch] = useReducer(
    onboardingReducer,
    undefined,
    () => createInitialOnboardingState('preview'),
  );
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const applyInFlightRef = useRef(false);
  const gutter = width <= 375 ? spacing.screenNarrow : spacing.screen;

  const api = useMemo(
    () =>
      new OnboardingApi(
        new ApiClient({ baseUrl: apiBaseUrl, tokenProvider: getAccessToken }),
      ),
    [getAccessToken],
  );

  const withSessionRefresh = useCallback(
    async <T,>(operation: () => Promise<T>): Promise<T> => {
      try {
        return await operation();
      } catch (error: unknown) {
        if (!(error instanceof ApiError) || error.kind !== 'authentication') {
          throw error;
        }
        const accessToken = await recoverAuthentication();
        if (!accessToken) throw error;
        return operation();
      }
    },
    [recoverAuthentication],
  );

  const load = useCallback(async () => {
    if (authState.status === 'hydrating' || authState.status === 'refreshing') {
      return;
    }
    if (authState.status !== 'authenticated') {
      onRequireSignIn();
      return;
    }
    setLoading(true);
    setLoadError(null);
    try {
      const serverState = await withSessionRefresh(() => api.getState());
      if (serverState.status === 'completed') {
        onComplete();
        return;
      }
      if (!serverState.preview || serverState.preview.status !== 'ready') {
        onEdit();
        return;
      }
      dispatch({
        type: 'server/restored',
        preview: serverState.preview,
        editing: false,
      });
    } catch {
      setLoadError('Не удалось загрузить первый ритм. Рассказ сохранён.');
    } finally {
      setLoading(false);
    }
  }, [
    api,
    authState.status,
    onComplete,
    onEdit,
    onRequireSignIn,
    withSessionRefresh,
  ]);

  useEffect(() => {
    void load();
  }, [load]);

  const apply = async () => {
    const preview = state.preview;
    const user = authState.user;
    if (!preview || !user || applyInFlightRef.current) return;
    applyInFlightRef.current = true;
    dispatch({ type: 'apply/submitted' });
    try {
      const applied = await withSessionRefresh(() =>
        api.apply({ previewId: preview.id, expectedVersion: preview.version }),
      );
      dispatch({ type: 'apply/succeeded', preview: applied });
      await new OnboardingDraftStore(AsyncStorage, user.publicId)
        .clear()
        .catch(() => undefined);
      onComplete();
    } catch {
      dispatch({
        type: 'apply/failed',
        message: 'Не удалось начать. Первый ритм сохранён — попробуйте ещё раз.',
      });
    } finally {
      applyInFlightRef.current = false;
    }
  };

  if (loading || !state.preview) {
    return (
      <SafeAreaView style={styles.safeArea}>
        <View style={styles.loading}>
          <Text accessibilityLiveRegion="polite" style={styles.loadingTitle}>
            {loadError ?? 'Открываю ваш первый ритм…'}
          </Text>
          {loadError ? (
            <Pressable accessibilityRole="button" onPress={() => void load()} style={styles.retry}>
              <Text style={styles.retryText}>Попробовать ещё раз</Text>
            </Pressable>
          ) : null}
        </View>
      </SafeAreaView>
    );
  }

  const preview = state.preview;
  return (
    <SafeAreaView edges={['top']} style={styles.safeArea}>
      <ScrollView
        contentContainerStyle={[
          styles.content,
          {
            paddingHorizontal: gutter,
            paddingBottom: Math.max(insets.bottom, spacing.md) + 96,
          },
        ]}
      >
        <Pressable
          accessibilityLabel="Изменить рассказ"
          accessibilityRole="button"
          disabled={state.step === 'applying'}
          onPress={onEdit}
          style={styles.backButton}
        >
          <Text style={styles.backText}>‹</Text>
        </Pressable>
        <Text style={styles.eyebrow}>Первый собранный план</Text>
        <Text accessibilityRole="header" style={styles.title}>
          Ваш ритм на {currentMonth()}
        </Text>
        <Text style={styles.lead}>
          Он опирается на ваш распорядок и доступное время. Ритм будет меняться
          вместе с вами — без выдуманных процентов прогресса.
        </Text>

        <View style={styles.path}>
          <View accessibilityElementsHidden style={styles.pathLine} />
          <View style={styles.pathContent}>
            {preview.allocation.goals.map((goal, index) => (
              <GoalRhythm goal={goal} index={index} key={`${goal.title}-${index}`} />
            ))}
          </View>
        </View>

        <RhythmSummary preview={preview} />

        {state.error ? (
          <Text accessibilityLiveRegion="polite" style={styles.error}>
            {state.error.message}
          </Text>
        ) : null}
      </ScrollView>

      <View
        style={[
          styles.bottomBar,
          {
            paddingHorizontal: gutter,
            paddingBottom: Math.max(insets.bottom, spacing.md),
          },
        ]}
      >
        <Pressable
          accessibilityRole="button"
          accessibilityState={{
            busy: state.step === 'applying',
            disabled: state.step === 'applying',
          }}
          disabled={state.step === 'applying'}
          onPress={() => void apply()}
          style={({ pressed }) => [
            styles.primaryButton,
            state.step === 'applying' && styles.disabled,
            pressed && styles.pressed,
          ]}
        >
          <Text style={styles.primaryButtonText}>
            {state.step === 'applying' ? 'Начинаю…' : 'Начать'}
          </Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          disabled={state.step === 'applying'}
          onPress={onEdit}
          style={styles.editButton}
        >
          <Text style={styles.editText}>Изменить рассказ</Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

function GoalRhythm({ goal, index }: { goal: GoalAllocation; index: number }) {
  return (
    <View style={styles.goalRow}>
      <View accessibilityElementsHidden style={styles.goalDot} />
      <View style={styles.goalCopy}>
        <Text style={styles.goalIndex}>Направление {index + 1}</Text>
        <Text style={styles.goalTitle}>{goal.title}</Text>
        <Text style={styles.goalTime}>{formatDuration(goal.minutes)} в неделю</Text>
      </View>
    </View>
  );
}

function RhythmSummary({ preview }: { preview: OnboardingPreview }) {
  const summary = preview.structuredSummary;
  const days = summary.availableDays
    .map((day) => dayNames[day])
    .filter(Boolean)
    .join(', ');
  return (
    <View style={styles.summary}>
      <Text style={styles.summaryCaption}>Основа недели</Text>
      {summary.workStart && summary.workEnd ? (
        <SummaryRow
          label="Работа"
          value={`${summary.workStart}–${summary.workEnd}`}
        />
      ) : null}
      {days ? <SummaryRow label="Доступные дни" value={days} /> : null}
      <SummaryRow
        label="Планируем"
        value={formatDuration(preview.allocation.plannedMinutes)}
      />
      <SummaryRow
        label="Оставляем свободно"
        value={`${formatDuration(preview.allocation.reservedMinutes)} · ${preview.allocation.reservePercent}%`}
      />
      {summary.sleepTime ? (
        <SummaryRow label="Сон около" value={summary.sleepTime} />
      ) : null}
    </View>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.summaryRow}>
      <Text style={styles.summaryLabel}>{label}</Text>
      <Text style={styles.summaryValue}>{value}</Text>
    </View>
  );
}

function formatDuration(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (!hours) return `${rest} мин`;
  if (!rest) return `${hours} ч`;
  return `${hours} ч ${rest} мин`;
}

function currentMonth(): string {
  return new Intl.DateTimeFormat('ru-RU', { month: 'long' }).format(new Date());
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: colors.paper },
  content: { flexGrow: 1, paddingTop: spacing.sm },
  backButton: {
    width: spacing.touch,
    height: spacing.touch,
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: -spacing.sm,
    marginBottom: spacing.md,
  },
  backText: { fontSize: 34, lineHeight: 38, color: colors.ink },
  eyebrow: {
    ...typography.caption,
    color: colors.burgundy,
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  title: { ...typography.detailTitle, color: colors.ink, marginTop: spacing.xs },
  lead: { ...typography.body, color: colors.muted, marginTop: spacing.md },
  path: { flexDirection: 'row', marginTop: 40 },
  pathLine: {
    width: 2,
    marginLeft: 5,
    marginRight: spacing.lg,
    backgroundColor: colors.burgundy,
  },
  pathContent: { flex: 1 },
  goalRow: {
    minHeight: 88,
    flexDirection: 'row',
    paddingBottom: spacing.lg,
  },
  goalDot: {
    width: 12,
    height: 12,
    marginLeft: -spacing.lg - 2,
    marginRight: spacing.md,
    marginTop: 3,
    borderRadius: radius.round,
    borderWidth: 2,
    borderColor: colors.burgundy,
    backgroundColor: colors.paper,
  },
  goalCopy: { flex: 1 },
  goalIndex: { ...typography.caption, color: colors.muted },
  goalTitle: { ...typography.rowTitle, color: colors.ink, marginTop: spacing.xxs },
  goalTime: { ...typography.body, color: colors.burgundy, marginTop: spacing.xxs },
  summary: {
    marginTop: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.rule,
  },
  summaryCaption: {
    ...typography.caption,
    color: colors.burgundy,
    marginTop: spacing.lg,
    marginBottom: spacing.xs,
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  summaryRow: {
    minHeight: 52,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.rule,
  },
  summaryLabel: { ...typography.body, flex: 1, color: colors.muted },
  summaryValue: {
    ...typography.bodyMedium,
    flexShrink: 1,
    color: colors.ink,
    textAlign: 'right',
  },
  bottomBar: {
    paddingTop: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.rule,
    backgroundColor: colors.paper,
  },
  primaryButton: {
    minHeight: 52,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.control,
    backgroundColor: colors.ink,
  },
  primaryButtonText: { ...typography.bodyMedium, color: colors.paper },
  editButton: {
    minHeight: spacing.touch,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: spacing.xxs,
  },
  editText: { ...typography.body, color: colors.burgundy },
  error: { ...typography.body, color: colors.burgundy, marginTop: spacing.md },
  loading: { flex: 1, justifyContent: 'center', paddingHorizontal: spacing.screen },
  loadingTitle: { ...typography.sectionTitle, color: colors.ink },
  retry: { minHeight: spacing.touch, justifyContent: 'center', marginTop: spacing.sm },
  retryText: { ...typography.bodyMedium, color: colors.burgundy },
  disabled: { opacity: 0.42 },
  pressed: { opacity: 0.72 },
});
