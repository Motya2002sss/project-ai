import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Pressable, RefreshControl, ScrollView, StyleSheet, Text,
  useWindowDimensions, View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { colors } from '../../theme/colors';
import { radius } from '../../theme/radius';
import { spacing } from '../../theme/spacing';
import { typography } from '../../theme/typography';
import { CaptureSheet } from '../capture/CaptureSheet';
import { usePlanner } from '../planner/PlannerProvider';
import { buildCalendarScreenModel, type CalendarMode } from './calendarModel';
import { useCalendarData } from './useCalendarData';

const modes: { id: CalendarMode; label: string }[] = [
  { id: 'day', label: 'День' }, { id: 'week', label: 'Неделя' }, { id: 'month', label: 'Месяц' },
];

function localToday(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

export function CalendarScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ date?: string }>();
  const initialDate = typeof params.date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(params.date)
    ? params.date : localToday();
  const [selectedDate, setSelectedDate] = useState(initialDate);
  const [mode, setMode] = useState<CalendarMode>('week');
  const { width } = useWindowDimensions();
  const { state, refresh, canRefresh } = useCalendarData(selectedDate);
  const planner = usePlanner();
  const captureStartedHere = useRef(false);
  const model = useMemo(() => buildCalendarScreenModel({
    mode, selectedDate, width, day: state.day, week: state.week, month: state.month,
    status: state.status, source: state.source,
    ...(state.errorMessage ? { errorMessage: state.errorMessage } : {}),
  }), [mode, selectedDate, state, width]);
  const gutter = width <= 375 ? spacing.screenNarrow : spacing.screen;

  useEffect(() => {
    if (!captureStartedHere.current || planner.state.capture.status !== 'success') return;
    captureStartedHere.current = false;
    router.replace('/');
  }, [planner.state.capture.status, router]);

  const openCapture = () => {
    captureStartedHere.current = true;
    planner.openCapture();
  };

  const closeCapture = () => {
    captureStartedHere.current = false;
    planner.closeCapture();
  };

  return (
    <SafeAreaView edges={['top', 'bottom']} style={styles.safeArea}>
      <View style={[styles.top, { paddingHorizontal: gutter }]}>
        <Pressable accessibilityRole="button" accessibilityLabel="Вернуться в Сегодня" onPress={() => router.back()} style={styles.back}>
          <Text style={styles.backText}>‹ Сегодня</Text>
        </Pressable>
        <Text accessibilityRole="header" style={styles.title}>Календарь</Text>
        <Text style={styles.range}>{model.state === 'ready' ? model.rangeLabel : 'План и ритм'}</Text>
        <View accessibilityRole="tablist" style={styles.segmented}>
          {modes.map((item) => (
            <Pressable key={item.id} accessibilityRole="tab" accessibilityState={{ selected: mode === item.id }} onPress={() => setMode(item.id)} style={[styles.segment, mode === item.id && styles.segmentSelected]}>
              <Text style={[styles.segmentLabel, mode === item.id && styles.segmentLabelSelected]}>{item.label}</Text>
            </Pressable>
          ))}
        </View>
      </View>

      <ScrollView
        contentContainerStyle={[styles.content, { paddingHorizontal: gutter }]}
        refreshControl={canRefresh ? <RefreshControl refreshing={state.status === 'loading' && state.source !== null} onRefresh={() => void refresh()} tintColor={colors.burgundy} /> : undefined}
      >
        {model.state === 'loading' ? <State title="Собираю сохранённый ритм…" /> : null}
        {model.state === 'error' ? <State title={model.message} copy="Сохранённых данных на устройстве нет." onRetry={canRefresh ? () => void refresh() : undefined} /> : null}
        {model.state === 'ready' ? (
          <>
            {model.notice ? <Text accessibilityLiveRegion="polite" style={styles.notice}>{model.notice}</Text> : null}
            {mode !== 'month' ? (
              <>
                <View style={styles.weekThread}>
                  <View accessibilityElementsHidden style={styles.threadLine} />
                  {model.weekDays.map((day) => (
                    <Pressable key={day.date} accessibilityRole="tab" accessibilityLabel={`${day.label}, ${day.day}`} accessibilityState={{ selected: day.selected }} onPress={() => setSelectedDate(day.date)} style={styles.dayButton}>
                      <Text style={[styles.dayName, day.selected && styles.daySelectedText]}>{day.label}</Text>
                      <View style={[styles.dayMarker, day.hasPlan && styles.dayMarkerPlanned, day.selected && styles.dayMarkerSelected]} />
                      <Text style={[styles.dayNumber, day.selected && styles.daySelectedText]}>{day.day}</Text>
                    </Pressable>
                  ))}
                </View>
                <View style={styles.timeline}>
                  {model.emptyMessage ? <State title={model.emptyMessage} copy={model.freeLabel ?? 'Здесь остаётся место для отдыха и изменений.'} /> : null}
                  {model.selectedItems.map((item) => (
                    <View key={item.id} accessible accessibilityLabel={`${item.timeLabel}. ${item.title}. ${item.kindLabel}`} style={styles.row}>
                      <View style={[styles.rowMarker, item.completed && styles.rowMarkerDone]} />
                      <View style={styles.rowBody}>
                        <View style={styles.rowMeta}><Text style={styles.rowTime}>{item.timeLabel}</Text><Text style={styles.rowKind}>{item.kindLabel}</Text></View>
                        <Text style={[styles.rowTitle, item.completed && styles.completed]}>{item.title}</Text>
                      </View>
                    </View>
                  ))}
                </View>
                {mode === 'week' && model.commitments.length > 0 ? (
                  <View style={styles.commitments}>
                    <Text style={styles.sectionLabel}>Ритм недели</Text>
                    {model.commitments.map((item) => <View key={item.id} style={styles.commitment}><Text style={styles.commitmentTitle}>{item.title}</Text><Text style={styles.commitmentDetail}>{item.detail}</Text></View>)}
                  </View>
                ) : null}
              </>
            ) : (
              <View style={styles.month}>
                <Text style={styles.monthSummary}>{model.monthSummary}</Text>
                {model.monthFacts.length === 0 ? <State title="В этом месяце нет ключевых отметок" /> : model.monthFacts.map((fact) => (
                  <View key={fact.id} style={styles.monthRow}><Text style={styles.monthDate}>{fact.dateLabel}</Text><View style={styles.monthBody}><Text style={styles.rowKind}>{fact.kind}</Text><Text style={styles.rowTitle}>{fact.title}</Text></View></View>
                ))}
              </View>
            )}
          </>
        ) : null}
      </ScrollView>

      <View style={[styles.captureArea, { paddingHorizontal: gutter }]}>
        <Pressable accessibilityRole="button" accessibilityLabel="Описать изменение недели" onPress={openCapture} style={({ pressed }) => [styles.captureButton, pressed && styles.capturePressed]}>
          <Text style={styles.capturePlus}>+</Text>
          <Text style={styles.captureText}>Что изменилось?</Text>
        </Pressable>
      </View>

      <CaptureSheet
        capture={planner.state.capture}
        draft={planner.state.draft}
        snapshot={planner.state.today.snapshot}
        onChangeDraft={planner.setDraft}
        onClose={closeCapture}
        onSubmit={planner.submitCapture}
        onRetry={planner.retryCapture}
        onRespond={planner.respondToInteraction}
      />
    </SafeAreaView>
  );
}

function State({ title, copy, onRetry }: { title: string; copy?: string; onRetry?: () => void }) {
  return <View style={styles.state}><Text style={styles.stateTitle}>{title}</Text>{copy ? <Text style={styles.stateCopy}>{copy}</Text> : null}{onRetry ? <Pressable accessibilityRole="button" onPress={onRetry} style={styles.retry}><Text style={styles.retryText}>Повторить</Text></Pressable> : null}</View>;
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: colors.paper }, top: { paddingTop: spacing.xs },
  back: { minHeight: spacing.touch, alignSelf: 'flex-start', justifyContent: 'center' }, backText: { ...typography.bodyMedium, color: colors.burgundy },
  title: { ...typography.screenTitle, color: colors.ink }, range: { ...typography.body, color: colors.muted, marginTop: spacing.xxs },
  segmented: { flexDirection: 'row', marginTop: spacing.lg, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.rule },
  segment: { flex: 1, minHeight: spacing.touch, justifyContent: 'center', alignItems: 'center', borderBottomWidth: 2, borderBottomColor: 'transparent' },
  segmentSelected: { borderBottomColor: colors.burgundy }, segmentLabel: { ...typography.body, color: colors.muted }, segmentLabelSelected: { ...typography.bodyMedium, color: colors.ink },
  content: { flexGrow: 1, paddingBottom: 48 }, notice: { ...typography.caption, color: colors.burgundy, marginTop: spacing.md },
  weekThread: { minHeight: 96, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginTop: spacing.lg, position: 'relative' },
  threadLine: { position: 'absolute', left: '7%', right: '7%', top: 39, height: StyleSheet.hairlineWidth, backgroundColor: colors.rule },
  dayButton: { width: '13.5%', minHeight: 72, alignItems: 'center', justifyContent: 'flex-start' }, dayName: { ...typography.caption, color: colors.muted }, dayNumber: { ...typography.bodyMedium, color: colors.ink, marginTop: spacing.xs }, daySelectedText: { color: colors.burgundy },
  dayMarker: { width: 7, height: 7, borderRadius: radius.round, marginTop: spacing.sm, backgroundColor: colors.paper, borderWidth: 1, borderColor: colors.rule }, dayMarkerPlanned: { backgroundColor: colors.muted, borderColor: colors.muted }, dayMarkerSelected: { width: 11, height: 11, marginTop: 10, backgroundColor: colors.burgundy, borderColor: colors.burgundy },
  timeline: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.rule }, row: { minHeight: 74, flexDirection: 'row', paddingVertical: spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.rule },
  rowMarker: { width: 8, height: 8, borderRadius: radius.round, backgroundColor: colors.burgundy, marginTop: 7, marginRight: spacing.md }, rowMarkerDone: { backgroundColor: colors.rule }, rowBody: { flex: 1 }, rowMeta: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', gap: spacing.xs }, rowTime: { ...typography.caption, ...typography.tabular, color: colors.ink }, rowKind: { ...typography.caption, color: colors.muted }, rowTitle: { ...typography.rowTitle, color: colors.ink, marginTop: spacing.xs }, completed: { color: colors.muted, textDecorationLine: 'line-through' },
  commitments: { marginTop: spacing.xl }, sectionLabel: { ...typography.caption, color: colors.burgundy, textTransform: 'uppercase', letterSpacing: 0.4 }, commitment: { paddingVertical: spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.rule }, commitmentTitle: { ...typography.bodyMedium, color: colors.ink }, commitmentDetail: { ...typography.caption, color: colors.muted, marginTop: spacing.xxs },
  month: { marginTop: spacing.xl }, monthSummary: { ...typography.body, color: colors.muted, marginBottom: spacing.lg }, monthRow: { flexDirection: 'row', paddingVertical: spacing.md, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.rule }, monthDate: { ...typography.caption, ...typography.tabular, color: colors.burgundy, width: 82, paddingTop: 2 }, monthBody: { flex: 1 },
  state: { paddingVertical: 48, maxWidth: 330 }, stateTitle: { ...typography.currentTitle, color: colors.ink }, stateCopy: { ...typography.body, color: colors.muted, marginTop: spacing.sm }, retry: { minHeight: spacing.touch, alignSelf: 'flex-start', justifyContent: 'center', paddingHorizontal: spacing.md, borderWidth: 1, borderColor: colors.rule, borderRadius: radius.control, marginTop: spacing.lg }, retryText: { ...typography.bodyMedium, color: colors.burgundy },
  captureArea: { paddingTop: spacing.sm, paddingBottom: spacing.sm, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.rule, backgroundColor: colors.paper },
  captureButton: { minHeight: 46, flexDirection: 'row', alignItems: 'center', gap: spacing.xs, paddingHorizontal: spacing.sm, borderWidth: 1, borderColor: colors.rule, borderRadius: radius.control },
  capturePressed: { backgroundColor: colors.softBurgundy }, capturePlus: { fontSize: 18, lineHeight: 21, color: colors.burgundy }, captureText: { ...typography.body, color: colors.muted },
});
