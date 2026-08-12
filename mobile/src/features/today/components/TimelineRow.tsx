import {
  type LayoutChangeEvent,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { colors } from '../../../theme/colors';
import { radius } from '../../../theme/radius';
import { spacing } from '../../../theme/spacing';
import { typography } from '../../../theme/typography';
import type { TimelineRowModel } from '../models';

interface TimelineRowProps {
  row: TimelineRowModel;
  pending: boolean;
  onOpen: (taskId: number) => void;
  onToggle: (taskId: number, completed: boolean) => void;
  onLayout?: (event: LayoutChangeEvent) => void;
}

export function TimelineRow({
  row,
  pending,
  onOpen,
  onToggle,
  onLayout,
}: TimelineRowProps) {
  const completed = row.variant === 'completed';
  const current = row.variant === 'current';
  const past = row.variant === 'past';
  return (
    <View
      onLayout={onLayout}
      style={[styles.row, current && styles.currentRow, past && styles.pastRow]}
    >
      {current ? <View accessibilityElementsHidden style={styles.nowMarker} /> : null}
      <Text style={[styles.time, current && styles.currentTime]}>
        {row.time ?? '—'}
      </Text>
      <View style={styles.markerColumn}>
        {row.isCompletable && row.taskId !== null ? (
          <Pressable
            accessibilityRole="checkbox"
            accessibilityLabel={`${row.title}. ${completed ? 'Выполнено' : 'Отметить выполненным'}`}
            accessibilityState={{ checked: completed, busy: pending, disabled: pending }}
            disabled={pending}
            hitSlop={0}
            onPress={() => onToggle(row.taskId!, completed)}
            style={styles.checkTarget}
          >
            <View
              style={[
                styles.check,
                current && styles.currentCheck,
                completed && styles.completedCheck,
              ]}
            >
              {completed ? <Text style={styles.checkmark}>✓</Text> : null}
              {current && !completed ? <View style={styles.currentDot} /> : null}
            </View>
          </Pressable>
        ) : (
          <View style={styles.checkTarget}>
            {row.time ? (
              <View
                accessibilityElementsHidden
                style={[
                  styles.passiveMarker,
                  current && styles.currentPassiveMarker,
                ]}
              />
            ) : null}
          </View>
        )}
      </View>
      {row.taskId !== null ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Открыть задачу ${row.title}`}
          onPress={() => onOpen(row.taskId!)}
          style={({ pressed }) => [
            styles.content,
            current && styles.currentContent,
            completed && styles.completedContent,
            pressed && styles.pressed,
          ]}
        >
          {row.label ? <Text style={styles.label}>{row.label}</Text> : null}
          {row.goalContext ? (
            <Text
              style={[
                styles.goalContext,
                current && styles.currentGoalContext,
                completed && styles.completedText,
              ]}
            >
              {row.goalContext}
            </Text>
          ) : null}
          <Text
            style={[
              styles.title,
              current && styles.currentTitle,
              completed && styles.completedText,
            ]}
          >
            {row.title}
          </Text>
          {row.meta ? (
            <Text style={[styles.meta, completed && styles.completedText]}>
              {row.meta}
            </Text>
          ) : null}
        </Pressable>
      ) : (
        <View style={[styles.content, current && styles.currentContent]}>
          {row.label ? <Text style={styles.label}>{row.label}</Text> : null}
          <Text style={[styles.title, styles.freeText]}>{row.title}</Text>
          {row.meta ? <Text style={styles.meta}>{row.meta}</Text> : null}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    minHeight: 66,
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  currentRow: { minHeight: 98 },
  nowMarker: {
    position: 'absolute',
    top: 0,
    right: 0,
    left: 68,
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.burgundy,
    opacity: 0.46,
  },
  pastRow: { opacity: 0.55 },
  time: {
    ...typography.caption,
    ...typography.tabular,
    width: 47,
    color: colors.muted,
    paddingTop: 1,
  },
  currentTime: { color: colors.burgundy, fontWeight: '500' },
  markerColumn: { width: spacing.touch, alignItems: 'center' },
  checkTarget: {
    width: spacing.touch,
    height: spacing.touch,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: -13,
  },
  check: {
    width: 26,
    height: 26,
    borderRadius: radius.round,
    borderWidth: 1,
    borderColor: colors.rule,
    backgroundColor: colors.paper,
    alignItems: 'center',
    justifyContent: 'center',
  },
  currentCheck: { borderColor: colors.burgundy },
  currentDot: {
    width: 6,
    height: 6,
    borderRadius: radius.round,
    backgroundColor: colors.burgundy,
  },
  passiveMarker: {
    width: 7,
    height: 7,
    borderRadius: radius.round,
    borderWidth: 1,
    borderColor: colors.rule,
    backgroundColor: colors.paper,
  },
  currentPassiveMarker: {
    width: 9,
    height: 9,
    borderColor: colors.burgundy,
    backgroundColor: colors.burgundy,
  },
  completedCheck: {
    borderColor: colors.ink,
    backgroundColor: colors.ink,
  },
  checkmark: { ...typography.caption, color: colors.paper, fontWeight: '500' },
  content: {
    flex: 1,
    minWidth: 0,
    minHeight: 54,
    paddingBottom: 17,
    paddingLeft: spacing.xs,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.rule,
  },
  currentContent: {
    marginTop: -9,
    paddingTop: 9,
    paddingRight: 10,
    paddingBottom: 12,
    paddingLeft: 10,
    borderBottomWidth: 0,
    borderLeftWidth: StyleSheet.hairlineWidth,
    borderLeftColor: colors.burgundy,
    borderRadius: radius.control,
    backgroundColor: colors.softBurgundy,
  },
  completedContent: { opacity: 0.66 },
  pressed: { opacity: 0.72 },
  label: {
    ...typography.caption,
    color: colors.burgundy,
    letterSpacing: 0.3,
    textTransform: 'uppercase',
    marginBottom: 5,
  },
  goalContext: {
    ...typography.caption,
    color: colors.muted,
    marginBottom: 3,
  },
  currentGoalContext: { color: colors.burgundy },
  title: { ...typography.rowTitle, color: colors.ink },
  currentTitle: { ...typography.currentTitle, color: colors.ink },
  meta: { ...typography.body, color: colors.muted, marginTop: 4 },
  completedText: { color: colors.muted },
  freeText: { color: colors.muted, fontWeight: '400' },
});
