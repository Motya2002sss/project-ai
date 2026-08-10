import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useMemo, useRef } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors } from '../../theme/colors';
import { radius } from '../../theme/radius';
import { spacing } from '../../theme/spacing';
import { typography } from '../../theme/typography';
import { usePlanner } from '../planner/PlannerProvider';
import { formatTime } from '../today/todayMapper';

function typeLabel(schedulingType: string): string {
  if (schedulingType === 'fixed') return 'Фиксированное событие';
  if (schedulingType === 'unscheduled') return 'Без времени';
  return 'Задача';
}

export function TaskDetailsScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { state, toggleTaskStatus } = usePlanner();
  const taskId = Number(id);
  const completionRequested = useRef(false);
  const snapshot = state.today.snapshot;
  const task = snapshot?.tasks.find((candidate) => candidate.id === taskId);
  const item = useMemo(
    () =>
      snapshot
        ? [...snapshot.scheduled_items, ...snapshot.unscheduled_items].find(
            (candidate) => candidate.task_id === taskId,
          )
        : undefined,
    [snapshot, taskId],
  );
  const pending = Boolean(state.completion.pendingByTask[taskId]);

  useEffect(() => {
    if (completionRequested.current && task?.status === 'done' && !pending) {
      router.back();
    }
  }, [pending, router, task?.status]);

  if (!task) {
    return (
      <SafeAreaView style={styles.safeArea}>
        <View style={styles.notFound}>
          <Text style={styles.notFoundTitle}>Задача недоступна</Text>
          <Pressable onPress={() => router.back()} style={styles.backTextButton}>
            <Text style={styles.backText}>Вернуться в Сегодня</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    );
  }

  const start = formatTime(item?.start_time ?? task.fixed_start);
  const end = formatTime(item?.end_time ?? task.fixed_end);
  const time = start ? `${start}${end ? ` — ${end}` : ''}` : 'Без времени';
  const completed = task.status === 'done';

  return (
    <SafeAreaView edges={['top']} style={styles.safeArea}>
      <View style={styles.topBar}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Назад в Сегодня"
          onPress={() => router.back()}
          style={styles.back}
        >
          <Text style={styles.backIcon}>‹</Text>
        </Pressable>
        <View style={styles.topBarCopy}>
          <Text style={styles.topBarTitle}>Задача</Text>
          <Text style={styles.topBarTime}>{time}</Text>
        </View>
      </View>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.kicker}>{typeLabel(task.scheduling_type)}</Text>
        <Text accessibilityRole="header" style={styles.title}>
          {task.title}
        </Text>
        {task.estimated_minutes ? (
          <View style={styles.fact}>
            <Text style={styles.factLabel}>Длительность</Text>
            <Text style={styles.factValue}>{task.estimated_minutes} минут</Text>
          </View>
        ) : null}
      </ScrollView>
      <View style={[styles.bottom, { paddingBottom: Math.max(insets.bottom, 16) }]}>
        {state.completion.error ? (
          <Text accessibilityLiveRegion="polite" style={styles.error}>
            {state.completion.error.message}
          </Text>
        ) : null}
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ disabled: completed || pending, busy: pending }}
          disabled={completed || pending}
          onPress={() => {
            completionRequested.current = true;
            toggleTaskStatus(task.id, 'planned');
          }}
          style={[styles.complete, (completed || pending) && styles.disabled]}
        >
          <Text style={styles.completeText}>
            {completed
              ? 'Задача выполнена'
              : pending
                ? 'Сохраняю…'
                : 'Завершить задачу'}
          </Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: colors.paper },
  topBar: {
    minHeight: 64,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.screen,
  },
  back: {
    width: spacing.touch,
    height: spacing.touch,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: radius.control,
  },
  backIcon: { fontSize: 30, lineHeight: 30, color: colors.ink },
  topBarCopy: { flex: 1 },
  topBarTitle: { ...typography.bodyMedium, color: colors.ink },
  topBarTime: {
    ...typography.caption,
    ...typography.tabular,
    color: colors.muted,
  },
  content: { flexGrow: 1, padding: spacing.screen, paddingTop: 52 },
  kicker: {
    ...typography.caption,
    color: colors.burgundy,
    textTransform: 'uppercase',
    letterSpacing: 0.4,
  },
  title: {
    ...typography.detailTitle,
    color: colors.ink,
    maxWidth: 340,
    marginTop: spacing.xs,
  },
  fact: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
    gap: spacing.md,
    marginTop: 40,
    paddingVertical: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: colors.rule,
  },
  factLabel: { ...typography.body, color: colors.muted },
  factValue: { ...typography.bodyMedium, ...typography.tabular, color: colors.ink },
  bottom: {
    paddingTop: spacing.sm,
    paddingHorizontal: spacing.screen,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.rule,
  },
  error: { ...typography.body, color: colors.burgundy, marginBottom: spacing.xs },
  complete: {
    minHeight: 52,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.control,
    backgroundColor: colors.ink,
  },
  completeText: { ...typography.bodyMedium, color: colors.paper },
  disabled: { opacity: 0.5 },
  notFound: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.screen,
  },
  notFoundTitle: { ...typography.sectionTitle, color: colors.ink },
  backTextButton: { minHeight: spacing.touch, justifyContent: 'center' },
  backText: { ...typography.bodyMedium, color: colors.burgundy },
});
