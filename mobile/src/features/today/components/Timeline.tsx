import { useCallback, useEffect, useRef } from 'react';
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
  onCurrentRowLayout?: (y: number) => void;
}

export function Timeline({
  model,
  pendingByTask,
  onOpenTask,
  onToggleTask,
  onCurrentRowLayout,
}: TimelineProps) {
  const rootYRef = useRef<number | null>(null);
  const timelineYRef = useRef<number | null>(null);
  const currentRowRef = useRef<{ id: number; y: number } | null>(null);
  const currentRowId = model.rows.find((row) => row.variant === 'current')?.id;
  const emitCurrentRowLayout = useCallback(() => {
    const currentRow = currentRowRef.current;
    if (
      !onCurrentRowLayout ||
      currentRowId === undefined ||
      currentRow?.id !== currentRowId ||
      rootYRef.current === null ||
      timelineYRef.current === null
    ) {
      return;
    }
    onCurrentRowLayout(rootYRef.current + timelineYRef.current + currentRow.y);
  }, [currentRowId, onCurrentRowLayout]);

  useEffect(() => {
    emitCurrentRowLayout();
  }, [emitCurrentRowLayout]);

  return (
    <View
      accessibilityLabel="План на день"
      onLayout={(event) => {
        rootYRef.current = event.nativeEvent.layout.y;
        emitCurrentRowLayout();
      }}
    >
      <View style={styles.heading}>
        <Text style={styles.headingTitle}>День</Text>
        {model.dayRange ? <Text style={styles.range}>{model.dayRange}</Text> : null}
      </View>
      <View
        onLayout={(event) => {
          timelineYRef.current = event.nativeEvent.layout.y;
          emitCurrentRowLayout();
        }}
        style={styles.timeline}
      >
        {model.rows.length > 0 ? <View style={styles.line} /> : null}
        {model.rows.map((row) => (
          <TimelineRow
            key={row.id}
            row={row}
            pending={row.taskId !== null && Boolean(pendingByTask[row.taskId])}
            onLayout={
              row.variant === 'current' && onCurrentRowLayout
                ? (event) => {
                    currentRowRef.current = {
                      id: row.id,
                      y: event.nativeEvent.layout.y,
                    };
                    emitCurrentRowLayout();
                  }
                : undefined
            }
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
    backgroundColor: colors.burgundy,
    opacity: 0.34,
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
