import { useRouter } from 'expo-router';
import { useMemo, useRef } from 'react';
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

import { CaptureSheet } from '../capture/CaptureSheet';
import { PlanDiffNotice } from '../capture/PlanDiffNotice';
import { ProcessingNotice } from '../capture/ProcessingNotice';
import { usePlanner } from '../planner/PlannerProvider';
import { mapDaySnapshot } from './todayMapper';
import { shouldOfferTodaySetup } from './todaySetupModel';
import {
  currentTimelineKey,
  timelineAutoScrollOffset,
} from './todayScrollModel';
import { Timeline } from './components/Timeline';
import { TodayHeader } from './components/TodayHeader';
import {
  AllDoneState,
  EmptyDayState,
  TodayErrorBanner,
  TodayLoadingState,
  TodayUnavailableState,
} from './components/TodayStates';
import { colors } from '../../theme/colors';
import { dogfoodRuntimeEnabled } from '../../config/environment';
import { radius } from '../../theme/radius';
import { spacing } from '../../theme/spacing';
import { typography } from '../../theme/typography';

export function TodayScreen() {
  const router = useRouter();
  const scrollRef = useRef<ScrollView>(null);
  const autoScrolledKeyRef = useRef<string | null>(null);
  const { width } = useWindowDimensions();
  const {
    state,
    completionOverrides,
    apiBaseUrl,
    openCapture,
    closeCapture,
    setDraft,
    submitCapture,
    respondToInteraction,
    retryCapture,
    retryCompletion,
    refreshToday,
    toggleTaskStatus,
  } = usePlanner();
  const snapshot = state.today.snapshot;
  const model = useMemo(
    () => (snapshot ? mapDaySnapshot(snapshot, completionOverrides) : null),
    [completionOverrides, snapshot],
  );
  const gutter = width <= 375 ? spacing.screenNarrow : spacing.screen;
  const capture = state.capture;
  const needsSetup =
    dogfoodRuntimeEnabled &&
    shouldOfferTodaySetup(apiBaseUrl, state.today.error?.message ?? null);
  const autoScrollKey = currentTimelineKey(model);

  const scrollToCurrentRow = (rowY: number) => {
    if (!autoScrollKey || autoScrolledKeyRef.current === autoScrollKey) return;
    autoScrolledKeyRef.current = autoScrollKey;
    scrollRef.current?.scrollTo({
      y: timelineAutoScrollOffset(rowY),
      animated: false,
    });
  };

  return (
    <SafeAreaView edges={['top']} style={styles.safeArea}>
      <ScrollView
        ref={scrollRef}
        contentContainerStyle={[
          styles.scrollContent,
          { paddingHorizontal: gutter },
        ]}
        keyboardDismissMode="interactive"
        refreshControl={
          <RefreshControl
            refreshing={state.today.refreshing && Boolean(snapshot)}
            onRefresh={refreshToday}
            tintColor={colors.burgundy}
          />
        }
      >
        <View style={styles.headerArea}>
          <TodayHeader
            dateLabel={model?.dateLabel ?? 'План на сегодня'}
            focusText={model?.focusText}
            progressLabel={model?.progressLabel}
            progressFraction={model?.progressFraction}
            weekProgressLabel={model?.weekProgressLabel}
            directionTitles={model?.directionTitles}
            onOpenCalendar={() =>
              snapshot
                ? router.push({ pathname: '/calendar', params: { date: snapshot.date } } as never)
                : router.push('/calendar')
            }
          />
          {capture.status === 'submitting' ? (
            <ProcessingNotice slow={capture.slow} />
          ) : null}
          {capture.status === 'success' && snapshot ? (
            <PlanDiffNotice
              diff={capture.planDiff}
              snapshot={snapshot}
              replyText={capture.replyText}
              didChange={capture.didChange}
            />
          ) : null}
          {state.today.error ? (
            <TodayErrorBanner
              message={state.today.error.message}
              onRetry={state.today.error.retryable ? refreshToday : undefined}
            />
          ) : null}
          {state.completion.error ? (
            <TodayErrorBanner
              message={state.completion.error.message}
              onRetry={
                state.completion.error.retryable ? retryCompletion : undefined
              }
            />
          ) : null}
          {needsSetup ? (
            <Pressable
              accessibilityRole="button"
              onPress={() => router.push('/setup')}
              style={styles.setupButton}
            >
              <Text style={styles.setupText}>Настроить доступ</Text>
            </Pressable>
          ) : null}
        </View>
        {!model && !state.today.error ? <TodayLoadingState /> : null}
        {!model && state.today.error ? <TodayUnavailableState /> : null}
        {model?.state === 'empty' ? <EmptyDayState /> : null}
        {model && model.state !== 'empty' ? (
          <Timeline
            model={model}
            pendingByTask={state.completion.pendingByTask}
            onOpenTask={(taskId) =>
              router.push({ pathname: '/task/[id]', params: { id: String(taskId) } })
            }
            onToggleTask={(taskId, completed) =>
              toggleTaskStatus(taskId, completed ? 'done' : 'planned')
            }
            onCurrentRowLayout={scrollToCurrentRow}
          />
        ) : null}
        {model?.state === 'allDone' ? <AllDoneState /> : null}
      </ScrollView>

      <View style={[styles.captureArea, { paddingHorizontal: gutter }]}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Описать, что изменилось"
          onPress={openCapture}
          style={({ pressed }) => [styles.captureButton, pressed && styles.pressed]}
        >
          <Text style={styles.plus}>+</Text>
          <Text style={styles.captureText}>Что изменилось?</Text>
        </Pressable>
      </View>

      <CaptureSheet
        capture={capture}
        draft={state.draft}
        snapshot={snapshot}
        onChangeDraft={setDraft}
        onClose={closeCapture}
        onSubmit={submitCapture}
        onRetry={retryCapture}
        onRespond={respondToInteraction}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: colors.paper },
  headerArea: { paddingTop: spacing.md },
  scrollContent: { flexGrow: 1, paddingBottom: spacing.lg },
  setupButton: {
    alignSelf: 'flex-start',
    minHeight: spacing.touch,
    justifyContent: 'center',
  },
  setupText: { ...typography.bodyMedium, color: colors.burgundy },
  captureArea: {
    paddingTop: spacing.sm,
    paddingBottom: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.rule,
    backgroundColor: colors.paper,
  },
  captureButton: {
    minHeight: 46,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    paddingHorizontal: spacing.sm,
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: radius.control,
  },
  plus: { fontSize: 18, lineHeight: 21, color: colors.burgundy },
  captureText: { ...typography.body, color: colors.muted },
  pressed: { backgroundColor: colors.softBurgundy },
});
