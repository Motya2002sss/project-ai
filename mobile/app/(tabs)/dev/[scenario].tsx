import { Redirect, useLocalSearchParams } from 'expo-router';
import { useMemo } from 'react';
import { ScrollView, StyleSheet, Text, useWindowDimensions, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { CaptureSheet } from '../../../src/features/capture/CaptureSheet';
import { PlanDiffNotice } from '../../../src/features/capture/PlanDiffNotice';
import { ProcessingNotice } from '../../../src/features/capture/ProcessingNotice';
import {
  allDoneDaySnapshot,
  appliedPlanDiff,
  captureStates,
  normalDaySnapshot,
} from '../../../src/dev/fixtures/daySnapshots';
import type { CaptureState } from '../../../src/features/planner/plannerReducer';
import { Timeline } from '../../../src/features/today/components/Timeline';
import { TodayHeader } from '../../../src/features/today/components/TodayHeader';
import {
  AllDoneState,
  TodayErrorBanner,
} from '../../../src/features/today/components/TodayStates';
import { mapDaySnapshot } from '../../../src/features/today/todayMapper';
import { colors } from '../../../src/theme/colors';
import { radius } from '../../../src/theme/radius';
import { spacing } from '../../../src/theme/spacing';
import { typography } from '../../../src/theme/typography';

type Scenario =
  | 'normal'
  | 'processing'
  | 'diff'
  | 'clarification'
  | 'confirmation'
  | 'conflict'
  | 'all-done'
  | 'offline';

const scenarios = new Set<Scenario>([
  'normal',
  'processing',
  'diff',
  'clarification',
  'confirmation',
  'conflict',
  'all-done',
  'offline',
]);

export default function DevScenarioRoute() {
  const { scenario: rawScenario } = useLocalSearchParams<{ scenario: string }>();
  const scenario = scenarios.has(rawScenario as Scenario)
    ? (rawScenario as Scenario)
    : 'normal';
  const { width } = useWindowDimensions();
  const gutter = width <= 375 ? spacing.screenNarrow : spacing.screen;
  const snapshot = scenario === 'all-done' ? allDoneDaySnapshot : normalDaySnapshot;
  const model = useMemo(() => mapDaySnapshot(snapshot), [snapshot]);
  let capture: CaptureState = { status: 'idle' };
  if (scenario === 'processing') capture = captureStates.processing;
  if (scenario === 'clarification') capture = captureStates.clarification;
  if (scenario === 'confirmation') capture = captureStates.confirmation;
  if (scenario === 'conflict') capture = captureStates.conflict;

  if (!__DEV__) return <Redirect href="/" />;

  return (
    <SafeAreaView edges={['top']} style={styles.safeArea}>
      <View style={[styles.header, { paddingHorizontal: gutter }]}>
        <TodayHeader dateLabel={model.dateLabel} />
        {scenario === 'processing' ? <ProcessingNotice slow /> : null}
        {scenario === 'diff' ? (
          <PlanDiffNotice
            diff={appliedPlanDiff}
            snapshot={snapshot}
            replyText="План обновлён."
            didChange
          />
        ) : null}
        {scenario === 'offline' ? (
          <TodayErrorBanner
            message="Нет соединения. Показываю сохранённый день."
            onRetry={() => undefined}
          />
        ) : null}
      </View>
      <ScrollView
        contentContainerStyle={[styles.content, { paddingHorizontal: gutter }]}
      >
        <Timeline
          model={model}
          pendingByTask={{}}
          onOpenTask={() => undefined}
          onToggleTask={() => undefined}
        />
        {scenario === 'all-done' ? <AllDoneState /> : null}
      </ScrollView>
      <View style={[styles.captureArea, { paddingHorizontal: gutter }]}>
        <View style={styles.captureButton}>
          <Text style={styles.plus}>+</Text>
          <Text style={styles.captureText}>Что изменилось?</Text>
        </View>
      </View>
      <CaptureSheet
        capture={capture}
        draft={
          scenario === 'clarification'
            ? 'добавь бжу чтобы я считал'
            : 'Сегодня задержусь на работе до 20'
        }
        snapshot={snapshot}
        onChangeDraft={() => undefined}
        onClose={() => undefined}
        onSubmit={() => undefined}
        onRetry={() => undefined}
        onRespond={() => undefined}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: colors.paper },
  header: { paddingTop: spacing.md },
  content: { flexGrow: 1, paddingBottom: spacing.lg },
  captureArea: {
    alignItems: 'flex-end',
    paddingTop: spacing.sm,
    paddingBottom: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.rule,
  },
  captureButton: {
    minHeight: 46,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    paddingHorizontal: 13,
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: radius.control,
  },
  plus: { fontSize: 18, color: colors.burgundy },
  captureText: { ...typography.body, color: colors.muted },
});
