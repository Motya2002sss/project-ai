import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors } from '../../../theme/colors';
import { typography } from '../../../theme/typography';

interface TodayHeaderProps {
  dateLabel: string;
  focusText?: string;
  progressLabel?: string;
  progressFraction?: number;
  weekProgressLabel?: string | null;
  directionTitles?: string[];
  onOpenCalendar?: () => void;
}

export function TodayHeader({
  dateLabel,
  focusText,
  progressLabel,
  progressFraction = 0,
  weekProgressLabel,
  directionTitles = [],
  onOpenCalendar,
}: TodayHeaderProps) {
  const progressWidth = `${Math.round(
    Math.min(1, Math.max(0, progressFraction)) * 100,
  )}%` as `${number}%`;
  return (
    <View accessibilityRole="header" style={styles.header}>
      <Text style={styles.date}>{dateLabel}</Text>
      <View style={styles.titleRow}>
        <Text style={styles.title}>Сегодня</Text>
        <View style={styles.titleActions}>
          {progressLabel ? <Text style={styles.progressLabel}>{progressLabel}</Text> : null}
          {onOpenCalendar ? (
            <Pressable accessibilityRole="button" accessibilityLabel="Открыть календарь" onPress={onOpenCalendar} hitSlop={6} style={styles.calendarButton}>
              <Text accessibilityElementsHidden style={styles.calendarIcon}>▦</Text>
            </Pressable>
          ) : null}
        </View>
      </View>
      {progressLabel ? (
        <View
          accessibilityLabel={`${progressLabel}. Прогресс дня`}
          accessibilityRole="progressbar"
          accessibilityValue={{
            min: 0,
            max: 100,
            now: Math.round(
              Math.min(1, Math.max(0, progressFraction)) * 100,
            ),
          }}
          style={styles.progressTrack}
        >
          <View style={[styles.progressValue, { width: progressWidth }]} />
        </View>
      ) : null}
      {weekProgressLabel ? (
        <Text style={styles.weekProgress}>{weekProgressLabel}</Text>
      ) : null}
      {focusText ? <Text style={styles.focus}>{focusText}</Text> : null}
      {directionTitles.length > 0 ? (
        <Text style={styles.directions}>{directionTitles.join(' · ')}</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  header: { alignItems: 'flex-start' },
  date: {
    ...typography.caption,
    color: colors.burgundy,
    letterSpacing: 0.4,
    textTransform: 'uppercase',
    marginBottom: 5,
  },
  titleRow: {
    width: '100%',
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'baseline',
    justifyContent: 'space-between',
    gap: 12,
  },
  title: { ...typography.screenTitle, color: colors.ink, flexShrink: 1 },
  titleActions: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  calendarButton: { minWidth: 44, minHeight: 44, alignItems: 'flex-end', justifyContent: 'center' },
  calendarIcon: { fontSize: 23, lineHeight: 26, color: colors.burgundy },
  progressLabel: {
    ...typography.caption,
    ...typography.tabular,
    color: colors.muted,
    textAlign: 'right',
  },
  progressTrack: {
    width: '100%',
    height: 2,
    overflow: 'hidden',
    marginTop: 10,
    backgroundColor: colors.rule,
  },
  progressValue: { height: '100%', backgroundColor: colors.burgundy },
  weekProgress: {
    ...typography.caption,
    ...typography.tabular,
    color: colors.muted,
    marginTop: 8,
  },
  focus: { ...typography.body, color: colors.ink, marginTop: 12 },
  directions: { ...typography.caption, color: colors.muted, marginTop: 6 },
});
