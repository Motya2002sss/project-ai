import { useRouter } from 'expo-router';
import { useMemo } from 'react';
import {
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useReduceMotion } from '../../accessibility/useReduceMotion';
import { colors } from '../../theme/colors';
import { radius } from '../../theme/radius';
import { spacing } from '../../theme/spacing';
import { typography } from '../../theme/typography';
import { PathGoalJourney } from './PathGoalJourney';
import { buildPathScreenModel } from './pathModel';
import { usePathData } from './usePathData';

export function PathScreen() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const reduceMotion = useReduceMotion();
  const { state, refresh, canRefresh } = usePathData();
  const gutter = width <= 375 ? spacing.screenNarrow : spacing.screen;
  const model = useMemo(
    () =>
      buildPathScreenModel({
        response: state.response,
        status: state.status,
        source: state.source,
        ...(state.errorMessage ? { errorMessage: state.errorMessage } : {}),
      }),
    [state.errorMessage, state.response, state.source, state.status],
  );
  const refreshing = state.status === 'loading' && state.response !== null;

  return (
    <SafeAreaView edges={['top']} style={styles.safeArea}>
      <ScrollView
        alwaysBounceVertical
        contentContainerStyle={[styles.content, { paddingHorizontal: gutter }]}
        refreshControl={
          canRefresh ? (
            <RefreshControl
              onRefresh={() => void refresh()}
              refreshing={refreshing}
              tintColor={colors.burgundy}
            />
          ) : undefined
        }
      >
        <View style={styles.header}>
          <Text accessibilityRole="header" style={styles.title}>
            Путь
          </Text>
          <Text style={styles.subtitle}>
            Только подтверждённый прогресс по главным целям
          </Text>
        </View>

        {model.state === 'loading' ? <PathLoading /> : null}
        {model.state === 'error' ? (
          <PathError
            canRetry={canRefresh}
            message={model.message}
            onRetry={() => void refresh()}
          />
        ) : null}
        {model.state === 'empty' ? (
          <PathEmpty notice={model.notice} />
        ) : null}
        {model.state === 'ready' ? (
          <View style={styles.goals}>
            {model.notice ? (
              <Text accessibilityLiveRegion="polite" style={styles.notice}>
                {model.notice}
              </Text>
            ) : null}
            {model.goals.map((goal) => (
              <View key={goal.id} style={styles.goalSection}>
                <PathGoalJourney
                  goal={goal}
                  onOpen={() =>
                    router.push({
                      pathname: '/goal/[id]',
                      params: { id: goal.id },
                    } as never)
                  }
                  reduceMotion={reduceMotion}
                />
              </View>
            ))}
          </View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

function PathLoading() {
  return (
    <View accessible accessibilityLabel="Загружаю путь" style={styles.state}>
      <View accessibilityElementsHidden style={styles.stateSeed}>
        <View style={styles.seedMarker} />
        <View style={styles.seedLine} />
      </View>
      <Text style={styles.stateEyebrow}>Синхронизация</Text>
      <Text style={styles.stateTitle}>Собираю подтверждённый путь…</Text>
    </View>
  );
}

function PathEmpty({ notice }: { notice: string | null }) {
  return (
    <View style={styles.state}>
      <View accessibilityElementsHidden style={styles.stateSeed}>
        <View style={styles.seedMarker} />
        <View style={styles.seedLine} />
      </View>
      {notice ? (
        <Text accessibilityLiveRegion="polite" style={styles.notice}>
          {notice}
        </Text>
      ) : null}
      <Text style={styles.stateEyebrow}>Долгосрочный маршрут</Text>
      <Text accessibilityRole="header" style={styles.stateTitle}>
        Здесь пока нет активных целей
      </Text>
      <Text style={styles.stateCopy}>
        Когда появится подтверждённая цель, здесь будут её этапы, текущая фаза,
        следующий шаг и фактические подтверждения прогресса.
      </Text>
    </View>
  );
}

function PathError({
  canRetry,
  message,
  onRetry,
}: {
  canRetry: boolean;
  message: string;
  onRetry: () => void;
}) {
  return (
    <View style={styles.state}>
      <Text style={styles.stateEyebrow}>Путь недоступен</Text>
      <Text accessibilityLiveRegion="polite" style={styles.stateTitle}>
        {message}
      </Text>
      <Text style={styles.stateCopy}>
        Сохранённых данных на устройстве нет. Прогресс не пересчитывался.
      </Text>
      {canRetry ? (
        <Pressable
          accessibilityRole="button"
          onPress={onRetry}
          style={({ pressed }) => [
            styles.retry,
            pressed && styles.retryPressed,
          ]}
        >
          <Text style={styles.retryLabel}>Повторить</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: colors.paper },
  content: {
    flexGrow: 1,
    paddingTop: spacing.md,
    paddingBottom: 48,
  },
  header: { maxWidth: 340 },
  title: { ...typography.screenTitle, color: colors.ink },
  subtitle: { ...typography.body, color: colors.muted, marginTop: spacing.xs },
  goals: { marginTop: 36 },
  goalSection: {
    paddingTop: spacing.sm,
    paddingBottom: spacing.xl,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.rule,
  },
  notice: {
    ...typography.caption,
    color: colors.burgundy,
    marginBottom: spacing.md,
  },
  state: { maxWidth: 336, marginTop: 64 },
  stateSeed: {
    height: 12,
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  seedMarker: {
    width: 10,
    height: 10,
    borderRadius: radius.round,
    backgroundColor: colors.burgundy,
  },
  seedLine: {
    flex: 1,
    height: StyleSheet.hairlineWidth,
    marginLeft: spacing.xs,
    backgroundColor: colors.rule,
  },
  stateEyebrow: {
    ...typography.caption,
    color: colors.burgundy,
    textTransform: 'uppercase',
    letterSpacing: 0.4,
  },
  stateTitle: {
    ...typography.currentTitle,
    color: colors.ink,
    marginTop: spacing.xs,
  },
  stateCopy: { ...typography.body, color: colors.muted, marginTop: spacing.sm },
  retry: {
    minHeight: spacing.touch,
    alignSelf: 'flex-start',
    justifyContent: 'center',
    marginTop: spacing.lg,
    paddingHorizontal: spacing.md,
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: radius.control,
  },
  retryPressed: { backgroundColor: colors.softBurgundy },
  retryLabel: { ...typography.bodyMedium, color: colors.burgundy },
});
