import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Crypto from 'expo-crypto';
import {
  AppState,
  type AppStateStatus,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  useWindowDimensions,
  View,
} from 'react-native';
import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from 'react';
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
import {
  applyBudgetHoursDraft,
  formatBudgetHours,
} from './budgetInput';
import {
  OnboardingDraftStore,
  type OnboardingDraft,
} from './onboardingDraftStorage';
import {
  createInitialOnboardingState,
  onboardingReducer,
  previewIdentityForMutation,
  type OnboardingRequestOrigin,
  type ResourceBudget,
  validateResourceBudget,
} from './onboardingReducer';

interface OnboardingScreenProps {
  editing?: boolean;
  textOnly?: boolean;
  onCompleted: () => void;
  onPreviewReady: () => void;
  onRequireSignIn: () => void;
}

const weekdays = [
  { value: 1, short: 'Пн' },
  { value: 2, short: 'Вт' },
  { value: 3, short: 'Ср' },
  { value: 4, short: 'Чт' },
  { value: 5, short: 'Пт' },
  { value: 6, short: 'Сб' },
  { value: 7, short: 'Вс' },
] as const;

export function OnboardingScreen({
  editing = false,
  textOnly = false,
  onCompleted,
  onPreviewReady,
  onRequireSignIn,
}: OnboardingScreenProps) {
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const { state: authState, getAccessToken, recoverAuthentication } = useAuth();
  const [state, dispatch] = useReducer(
    onboardingReducer,
    undefined,
    () => createInitialOnboardingState('narrative'),
  );
  const [storageReady, setStorageReady] = useState(textOnly);
  const [initialError, setInitialError] = useState<string | null>(null);
  const [budgetError, setBudgetError] = useState<string | null>(null);
  const stateRef = useRef(state);
  const requestInFlightRef = useRef(false);
  const draftStoreRef = useRef<OnboardingDraftStore | null>(null);
  stateRef.current = state;
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

  useEffect(() => {
    const listener = (next: AppStateStatus) => {
      if (next !== 'active') dispatch({ type: 'app/backgrounded' });
    };
    const subscription = AppState.addEventListener('change', listener);
    return () => subscription.remove();
  }, []);

  useEffect(() => {
    if (textOnly) return;
    if (authState.status === 'hydrating' || authState.status === 'refreshing') {
      return;
    }
    if (authState.status !== 'authenticated' || !authState.user) {
      onRequireSignIn();
      return;
    }
    let active = true;
    const store = new OnboardingDraftStore(AsyncStorage, authState.user.publicId);
    draftStoreRef.current = store;
    void (async () => {
      try {
        const draft = await store.load();
        if (active && draft) dispatch({ type: 'draft/hydrated', draft });
        const serverState = await withSessionRefresh(() => api.getState());
        if (!active) return;
        if (serverState.status === 'completed' && !editing) {
          onCompleted();
          return;
        }
        if (serverState.preview) {
          dispatch({
            type: 'server/restored',
            preview: serverState.preview,
            editing,
          });
        }
      } catch {
        if (active) {
          setInitialError(
            'Не удалось проверить onboarding. Рассказ на устройстве сохранён.',
          );
        }
      } finally {
        if (active) setStorageReady(true);
      }
    })();
    return () => {
      active = false;
    };
  }, [
    api,
    authState.status,
    authState.user,
    editing,
    onCompleted,
    onRequireSignIn,
    textOnly,
    withSessionRefresh,
  ]);

  useEffect(() => {
    if (!storageReady || !draftStoreRef.current) return;
    const draft: OnboardingDraft = {
      narrative: state.narrative,
      clarificationAnswer: state.clarificationAnswer,
      resourceBudget: state.resourceBudget,
      budgetConfirmed: state.budgetConfirmed,
    };
    void draftStoreRef.current.save(draft).catch(() => undefined);
  }, [
    state.budgetConfirmed,
    state.clarificationAnswer,
    state.narrative,
    state.resourceBudget,
    storageReady,
  ]);

  useEffect(() => {
    if (state.step === 'preview') onPreviewReady();
    if (state.step === 'completed') onCompleted();
  }, [onCompleted, onPreviewReady, state.step]);

  const requestFailure = useCallback(
    (requestId: string, error: unknown) => {
      const reason =
        error instanceof ApiError &&
        (error.kind === 'network' || error.kind === 'timeout')
          ? 'offline'
          : error instanceof ApiError && error.kind === 'authentication'
            ? 'authentication'
            : 'server';
      const message =
        reason === 'offline'
          ? 'Нет связи. Рассказ сохранён на устройстве.'
          : reason === 'authentication'
            ? 'Сессия завершена. Войдите снова.'
            : 'Не получилось собрать план. Попробуйте ещё раз.';
      dispatch({ type: 'request/failed', requestId, reason, message });
    },
    [],
  );

  const sendPreview = useCallback(
    async (requestId: string, origin: OnboardingRequestOrigin) => {
      if (requestInFlightRef.current || textOnly) return;
      const current = stateRef.current;
      const narrative = [
        current.narrative.trim(),
        current.clarificationAnswer.trim()
          ? `Мои цели: ${current.clarificationAnswer.trim()}.`
          : '',
      ]
        .filter(Boolean)
        .join('\n');
      if (!narrative) return;
      requestInFlightRef.current = true;
      dispatch({ type: 'preview/submitted', requestId, origin });
      try {
        const preview = await withSessionRefresh(() =>
          api.preview({
            requestId,
            narrative,
            resourceBudget: current.resourceBudget,
            ...previewIdentityForMutation(current.preview),
          }),
        );
        dispatch({ type: 'preview/received', requestId, preview });
      } catch (error: unknown) {
        requestFailure(requestId, error);
      } finally {
        requestInFlightRef.current = false;
      }
    },
    [api, requestFailure, textOnly, withSessionRefresh],
  );

  const submitNarrative = () => {
    if (!state.narrative.trim() || requestInFlightRef.current) return;
    void sendPreview(Crypto.randomUUID(), 'narrative');
  };

  const submitBudget = () => {
    const validation = validateResourceBudget(state.resourceBudget);
    if (validation) {
      setBudgetError(validation);
      return;
    }
    setBudgetError(null);
    void sendPreview(Crypto.randomUUID(), 'resource_budget');
  };

  const retry = () => {
    if (!state.retryRequestId || !state.retryOrigin) return;
    const requestId = state.retryRequestId;
    const origin = state.retryOrigin;
    dispatch({ type: 'request/retried' });
    void sendPreview(requestId, origin);
  };

  const changeBudget = (value: Partial<ResourceBudget>) => {
    setBudgetError(null);
    dispatch({ type: 'budget/changed', value });
  };

  const toggleAvailableDay = (day: number) => {
    const selected = state.resourceBudget.availableDays.includes(day);
    const availableDays = selected
      ? state.resourceBudget.availableDays.filter((value) => value !== day)
      : [...state.resourceBudget.availableDays, day].sort();
    changeBudget({
      availableDays,
      freeEvenings: state.resourceBudget.freeEvenings.filter((value) =>
        availableDays.includes(value),
      ),
    });
  };

  const toggleFreeEvening = (day: number) => {
    if (!state.resourceBudget.availableDays.includes(day)) return;
    const selected = state.resourceBudget.freeEvenings.includes(day);
    changeBudget({
      freeEvenings: selected
        ? state.resourceBudget.freeEvenings.filter((value) => value !== day)
        : [...state.resourceBudget.freeEvenings, day].sort(),
    });
  };

  const bottomPadding = Math.max(insets.bottom, spacing.md);

  if (!storageReady && !textOnly) {
    return (
      <SafeAreaView style={styles.safeArea}>
        <View accessible accessibilityLabel="Загружаю onboarding" style={styles.loadingState}>
          <Text style={styles.loadingTitle}>Возвращаю ваш рассказ…</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView edges={['top']} style={styles.safeArea}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.keyboard}
      >
        <ScrollView
          contentContainerStyle={[
            styles.content,
            { paddingHorizontal: gutter, paddingBottom: bottomPadding + 80 },
          ]}
          keyboardDismissMode="interactive"
          keyboardShouldPersistTaps="handled"
        >
          {state.step !== 'processing' ? (
            <Pressable
              accessibilityLabel="Назад"
              accessibilityRole="button"
              onPress={() => {
                if (state.step === 'narrative') onRequireSignIn();
                else dispatch({ type: 'navigation/back' });
              }}
              style={styles.backButton}
            >
              <Text style={styles.backText}>‹</Text>
            </Pressable>
          ) : null}

          {state.step === 'narrative' ? (
            <NarrativeStage
              error={state.error?.message ?? initialError}
              narrative={state.narrative}
              onChange={(value) =>
                dispatch({ type: 'narrative/changed', value })
              }
              onRetry={state.retryRequestId ? retry : undefined}
              textOnly={textOnly}
            />
          ) : null}

          {state.step === 'clarification' ? (
            <ClarificationStage
              answer={state.clarificationAnswer}
              onChange={(value) =>
                dispatch({ type: 'clarification/changed', value })
              }
              question={
                state.preview?.clarification?.question ??
                'Что для вас важнее всего в ближайшие месяцы?'
              }
            />
          ) : null}

          {state.step === 'resource_budget' ? (
            <BudgetStage
              budget={state.resourceBudget}
              error={budgetError ?? state.error?.message ?? null}
              onChange={changeBudget}
              onToggleAvailable={toggleAvailableDay}
              onToggleEvening={toggleFreeEvening}
            />
          ) : null}

          {state.step === 'processing' ? (
            <View accessibilityLiveRegion="polite" style={styles.processing}>
              <View accessibilityElementsHidden style={styles.processingLine} />
              <Text accessibilityRole="header" style={styles.title}>
                Собираю план…
              </Text>
              <Text style={styles.lead}>
                Сверяю распорядок, цели и доступное время. Рассказ уже сохранён.
              </Text>
            </View>
          ) : null}
        </ScrollView>

        <View style={[styles.bottomBar, { paddingBottom: bottomPadding, paddingHorizontal: gutter }]}>
          {state.step === 'narrative' ? (
            <PrimaryButton
              disabled={!state.narrative.trim() || textOnly}
              label={textOnly ? 'Нужен вход на iPhone' : 'Собрать мой план'}
              onPress={submitNarrative}
            />
          ) : null}
          {state.step === 'clarification' ? (
            <PrimaryButton
              disabled={!state.clarificationAnswer.trim()}
              label="Продолжить"
              onPress={() => dispatch({ type: 'clarification/continued' })}
            />
          ) : null}
          {state.step === 'resource_budget' ? (
            <PrimaryButton label="Показать мой ритм" onPress={submitBudget} />
          ) : null}
          {state.step === 'processing' ? (
            <PrimaryButton disabled label="Собираю план…" onPress={() => undefined} />
          ) : null}
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function NarrativeStage({
  error,
  narrative,
  onChange,
  onRetry,
  textOnly,
}: {
  error: string | null;
  narrative: string;
  onChange: (value: string) => void;
  onRetry?: () => void;
  textOnly: boolean;
}) {
  return (
    <View>
      <Text style={styles.eyebrow}>Ваш текущий ритм</Text>
      <Text accessibilityRole="header" style={styles.title}>
        Расскажите, как вы живёте
      </Text>
      <Text style={styles.lead}>
        Обычный день, свободное время и цели — своими словами.
      </Text>
      <TextInput
        accessibilityLabel="Рассказ о распорядке и целях"
        autoCapitalize="sentences"
        maxLength={12000}
        multiline
        onChangeText={onChange}
        placeholder="Например: работаю с 10 до 19, дорога по часу. В понедельник и среду свободен вечером. Хочу три раза ходить в зал и развиваться в backend-разработке."
        placeholderTextColor={colors.muted}
        scrollEnabled
        style={styles.narrativeInput}
        textAlignVertical="top"
        value={narrative}
      />
      <View style={styles.inputMeta}>
        <Text style={styles.inputMode}>Сейчас доступен текст</Text>
        <Text style={styles.inputCount}>{narrative.length}/12000</Text>
      </View>
      {textOnly ? (
        <Text style={styles.notice}>
          Это локальный текстовый режим. Он не создаёт пользователя и не
          показывает фиктивный план.
        </Text>
      ) : null}
      {error ? (
        <View style={styles.errorBlock}>
          <Text accessibilityLiveRegion="polite" style={styles.error}>
            {error}
          </Text>
          {onRetry ? (
            <Pressable accessibilityRole="button" onPress={onRetry} style={styles.retryButton}>
              <Text style={styles.retryText}>Попробовать ещё раз</Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

function ClarificationStage({
  answer,
  onChange,
  question,
}: {
  answer: string;
  onChange: (value: string) => void;
  question: string;
}) {
  return (
    <View>
      <Text style={styles.eyebrow}>Одно уточнение</Text>
      <Text accessibilityRole="header" style={styles.title}>
        {question}
      </Text>
      <Text style={styles.lead}>
        Назовите до трёх направлений. Остальные можно добавить позже.
      </Text>
      <TextInput
        accessibilityLabel="Ответ на уточнение"
        maxLength={2000}
        multiline
        onChangeText={onChange}
        placeholder="Например: карьера, набор веса и растяжка"
        placeholderTextColor={colors.muted}
        style={styles.clarificationInput}
        textAlignVertical="top"
        value={answer}
      />
    </View>
  );
}

function BudgetStage({
  budget,
  error,
  onChange,
  onToggleAvailable,
  onToggleEvening,
}: {
  budget: ResourceBudget;
  error: string | null;
  onChange: (value: Partial<ResourceBudget>) => void;
  onToggleAvailable: (day: number) => void;
  onToggleEvening: (day: number) => void;
}) {
  return (
    <View>
      <Text style={styles.eyebrow}>Реальные ресурсы</Text>
      <Text accessibilityRole="header" style={styles.title}>
        Сколько места оставить целям?
      </Text>
      <Text style={styles.lead}>
        Укажите время, которое действительно есть. 20% останутся свободными,
        чтобы неделя не ломалась от одного изменения.
      </Text>

      <BudgetNumberField
        label="Всего доступно в неделю"
        minutes={budget.weeklyAvailableMinutes}
        onChange={(weeklyAvailableMinutes) => onChange({ weeklyAvailableMinutes })}
      />

      <Text style={styles.fieldLabel}>Доступные дни</Text>
      <DayPicker
        selected={budget.availableDays}
        onToggle={onToggleAvailable}
      />

      <Text style={styles.fieldLabel}>Свободные вечера</Text>
      <DayPicker
        available={budget.availableDays}
        selected={budget.freeEvenings}
        onToggle={onToggleEvening}
      />

      <View style={styles.volumeGrid}>
        <BudgetNumberField
          compact
          label="Минимум"
          minutes={budget.minimumMinutes}
          onChange={(minimumMinutes) => onChange({ minimumMinutes })}
        />
        <BudgetNumberField
          compact
          label="Комфортно"
          minutes={budget.comfortableMinutes}
          onChange={(comfortableMinutes) => onChange({ comfortableMinutes })}
        />
        <BudgetNumberField
          compact
          label="Максимум"
          minutes={budget.maximumMinutes}
          onChange={(maximumMinutes) => onChange({ maximumMinutes })}
        />
      </View>

      {error ? (
        <Text accessibilityLiveRegion="polite" style={styles.error}>
          {error}
        </Text>
      ) : null}
    </View>
  );
}

function BudgetNumberField({
  compact = false,
  label,
  minutes,
  onChange,
}: {
  compact?: boolean;
  label: string;
  minutes: number;
  onChange: (minutes: number) => void;
}) {
  const [draft, setDraft] = useState(() => formatBudgetHours(minutes));
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (!focused) setDraft(formatBudgetHours(minutes));
  }, [focused, minutes]);

  return (
    <View style={[styles.numberField, compact && styles.compactNumberField]}>
      <Text style={styles.numberLabel}>{label}</Text>
      <View style={styles.numberControl}>
        <TextInput
          accessibilityLabel={`${label}, часов`}
          keyboardType="decimal-pad"
          onChangeText={(value) => {
            const next = applyBudgetHoursDraft(value, minutes);
            setDraft(next.text);
            if (next.minutes !== minutes) onChange(next.minutes);
          }}
          onBlur={() => {
            setFocused(false);
            setDraft(formatBudgetHours(minutes));
          }}
          onFocus={() => setFocused(true)}
          selectTextOnFocus
          style={styles.numberInput}
          value={draft}
        />
        <Text style={styles.numberUnit}>ч</Text>
      </View>
    </View>
  );
}

function DayPicker({
  available,
  selected,
  onToggle,
}: {
  available?: number[];
  selected: number[];
  onToggle: (day: number) => void;
}) {
  return (
    <View style={styles.dayPicker}>
      {weekdays.map((day) => {
        const enabled = !available || available.includes(day.value);
        const isSelected = selected.includes(day.value);
        return (
          <Pressable
            accessibilityLabel={day.short}
            accessibilityRole="button"
            accessibilityState={{ disabled: !enabled, selected: isSelected }}
            disabled={!enabled}
            key={day.value}
            onPress={() => onToggle(day.value)}
            style={[
              styles.day,
              isSelected && styles.daySelected,
              !enabled && styles.dayDisabled,
            ]}
          >
            <Text style={[styles.dayText, isSelected && styles.dayTextSelected]}>
              {day.short}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

function PrimaryButton({
  disabled = false,
  label,
  onPress,
}: {
  disabled?: boolean;
  label: string;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.primaryButton,
        disabled && styles.disabled,
        pressed && styles.pressed,
      ]}
    >
      <Text style={styles.primaryButtonText}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: colors.paper },
  keyboard: { flex: 1 },
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
  title: {
    ...typography.detailTitle,
    color: colors.ink,
    marginTop: spacing.xs,
  },
  lead: { ...typography.body, color: colors.muted, marginTop: spacing.md },
  narrativeInput: {
    minHeight: 236,
    maxHeight: 360,
    marginTop: spacing.xl,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: radius.input,
    backgroundColor: colors.raised,
    color: colors.ink,
    ...typography.body,
  },
  clarificationInput: {
    minHeight: 132,
    marginTop: spacing.xl,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: radius.input,
    backgroundColor: colors.raised,
    color: colors.ink,
    ...typography.body,
  },
  inputMeta: {
    minHeight: spacing.touch,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  inputMode: { ...typography.caption, color: colors.burgundy },
  inputCount: { ...typography.caption, color: colors.muted },
  notice: {
    ...typography.body,
    color: colors.muted,
    marginTop: spacing.md,
    paddingVertical: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: colors.rule,
  },
  processing: { flex: 1, paddingTop: 96 },
  processingLine: {
    width: 2,
    height: 96,
    marginBottom: spacing.xl,
    backgroundColor: colors.burgundy,
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
    paddingHorizontal: spacing.md,
    borderRadius: radius.control,
    backgroundColor: colors.ink,
  },
  primaryButtonText: { ...typography.bodyMedium, color: colors.paper },
  errorBlock: { marginTop: spacing.md },
  error: { ...typography.body, color: colors.burgundy, marginTop: spacing.md },
  retryButton: {
    minHeight: spacing.touch,
    alignSelf: 'flex-start',
    justifyContent: 'center',
    marginTop: spacing.xs,
  },
  retryText: { ...typography.bodyMedium, color: colors.burgundy },
  fieldLabel: { ...typography.bodyMedium, color: colors.ink, marginTop: spacing.xl },
  dayPicker: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: spacing.xs,
  },
  day: {
    width: spacing.touch,
    height: spacing.touch,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: radius.round,
  },
  daySelected: { borderColor: colors.burgundy, backgroundColor: colors.softBurgundy },
  dayDisabled: { opacity: 0.3 },
  dayText: { ...typography.caption, color: colors.muted },
  dayTextSelected: { color: colors.burgundy, fontWeight: '500' },
  numberField: {
    minHeight: 66,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: spacing.xl,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.rule,
  },
  compactNumberField: { flex: 1, marginTop: 0, flexDirection: 'column', alignItems: 'stretch' },
  numberLabel: { ...typography.body, color: colors.ink },
  numberControl: { flexDirection: 'row', alignItems: 'center' },
  numberInput: {
    minWidth: 48,
    minHeight: spacing.touch,
    paddingHorizontal: spacing.xs,
    color: colors.ink,
    textAlign: 'right',
    ...typography.rowTitle,
  },
  numberUnit: { ...typography.body, color: colors.muted },
  volumeGrid: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.xl },
  loadingState: { flex: 1, justifyContent: 'center', paddingHorizontal: spacing.screen },
  loadingTitle: { ...typography.sectionTitle, color: colors.ink },
  disabled: { opacity: 0.38 },
  pressed: { opacity: 0.72 },
});
