import { StyleSheet, Text, View } from 'react-native';

import type { TaskStatus } from '../../../api/types';
import { colors } from '../../../theme/colors';
import { spacing } from '../../../theme/spacing';
import { typography } from '../../../theme/typography';
import type { TodayModel } from '../models';
import { TimelineRow } from './TimelineRow';

interface TimelineProps {
  model: TodayModel;
  pendingByTask: Readonly<
    Record<number, { operationId: string; targetStatus: TaskStatus }>
  >;
  onOpenTask: (taskId: number) => void;
  onToggleTask: (taskId: number, completed: boolean) => void;
}

export function Timeline({
  model,
  pendingByTask,
  onOpenTask,
  onToggleTask,
}: TimelineProps) {
  return (
    <View accessibilityLabel="План на день">
      <View style={styles.heading}>
        <Text style={styles.headingTitle}>День</Text>
        {model.dayRange ? <Text style={styles.range}>{model.dayRange}</Text> : null}
      </View>
      <View style={styles.timeline}>
        {model.rows.length > 0 ? <View style={styles.line} /> : null}
        {model.rows.map((row) => (
          <TimelineRow
            key={row.id}
            row={row}
            pending={row.taskId !== null && Boolean(pendingByTask[row.taskId])}
            onOpen={onOpenTask}
            onToggle={onToggleTask}
          />
        ))}
      </View>
      {model.unscheduled.length > 0 ? (
        <View style={styles.unscheduled}>
          <Text style={styles.unscheduledTitle}>Без времени</Text>
          {model.unscheduled.map((row) => (
            <TimelineRow
              key={`unscheduled-${row.id}`}
              row={row}
              pending={row.taskId !== null && Boolean(pendingByTask[row.taskId])}
              onOpen={onOpenTask}
              onToggle={onToggleTask}
            />
          ))}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  heading: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
    gap: spacing.sm,
    marginTop: spacing.xl,
    marginBottom: spacing.sm,
  },
  headingTitle: { ...typography.sectionTitle, color: colors.ink },
  range: { ...typography.caption, ...typography.tabular, color: colors.muted },
  timeline: { position: 'relative' },
  line: {
    position: 'absolute',
    top: 12,
    bottom: 26,
    left: 69,
    width: StyleSheet.hairlineWidth,
    backgroundColor: colors.rule,
  },
  unscheduled: { marginTop: spacing.lg },
  unscheduledTitle: {
    ...typography.caption,
    color: colors.muted,
    textTransform: 'uppercase',
    letterSpacing: 0.3,
    marginBottom: spacing.sm,
  },
});
