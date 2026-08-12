import { useEffect, useRef, type ReactNode } from 'react';
import {
  Animated,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { colors } from '../../theme/colors';
import { motion } from '../../theme/motion';
import { radius } from '../../theme/radius';
import { spacing } from '../../theme/spacing';
import { typography } from '../../theme/typography';
import type { PathGoalModel } from './pathModel';

interface PathGoalJourneyProps {
  goal: PathGoalModel;
  onOpen: () => void;
  reduceMotion: boolean;
}

export function PathGoalJourney({
  goal,
  onOpen,
  reduceMotion,
}: PathGoalJourneyProps) {
  return (
    <Pressable
      accessible
      accessibilityHint="Показывает все данные и историю подтверждений"
      accessibilityLabel={goal.accessibilityLabel}
      accessibilityRole="button"
      onPress={onOpen}
      style={({ pressed }) => [styles.pressable, pressed && styles.pressed]}
    >
      <View accessibilityElementsHidden style={styles.line} />
      <JourneyNode marker="goal">
        <View style={styles.goalHeading}>
          <Text style={styles.goalTitle}>{goal.title}</Text>
          <ProgressReveal label={goal.progressLabel} reduceMotion={reduceMotion} />
        </View>
        <Text style={styles.formula}>{goal.progressExplanation}</Text>
      </JourneyNode>

      {goal.milestones.length > 0 ? (
        goal.milestones.map((milestone) => (
          <JourneyNode
            key={milestone.id}
            marker={milestone.status === 'completed' ? 'completed' : 'regular'}
          >
            <Text style={styles.nodeEyebrow}>{milestone.statusLabel}</Text>
            <Text style={styles.nodeTitle}>{milestone.title}</Text>
            {milestone.description ? (
              <Text style={styles.nodeCopy}>{milestone.description}</Text>
            ) : null}
          </JourneyNode>
        ))
      ) : (
        <JourneyNode marker="quiet">
          <Text style={styles.nodeEyebrow}>Этапы</Text>
          <Text style={styles.nodeCopy}>Этапы пока не определены</Text>
        </JourneyNode>
      )}

      <JourneyNode marker={goal.currentPhase ? 'current' : 'quiet'}>
        <Text style={styles.nodeEyebrow}>Текущая фаза</Text>
        {goal.currentPhase ? (
          <>
            <Text style={styles.nodeTitle}>{goal.currentPhase.title}</Text>
            {goal.currentPhase.programName ? (
              <Text style={styles.nodeCopy}>
                {goal.currentPhase.programName}
              </Text>
            ) : null}
          </>
        ) : (
          <Text style={styles.nodeCopy}>Фаза пока не определена</Text>
        )}
      </JourneyNode>

      <JourneyNode marker={goal.nextStep ? 'current' : 'quiet'}>
        <Text style={styles.nodeEyebrow}>Следующий шаг</Text>
        {goal.nextStep ? (
          <>
            <Text style={styles.nodeTitle}>{goal.nextStep.title}</Text>
            <Text style={styles.nodeCopy}>{goal.nextStep.detail}</Text>
          </>
        ) : (
          <Text style={styles.nodeCopy}>Следующий шаг пока не определён</Text>
        )}
      </JourneyNode>

      <JourneyNode
        marker={goal.recentEvidence.length > 0 ? 'completed' : 'quiet'}
      >
        <Text style={styles.nodeEyebrow}>Последние подтверждения</Text>
        {goal.recentEvidence.length > 0 ? (
          goal.recentEvidence.map((evidence) => (
            <View key={evidence.id} style={styles.evidenceRow}>
              <Text style={styles.nodeTitle}>{evidence.typeLabel}</Text>
              <Text style={styles.nodeCopy}>
                {[evidence.value, formatEvidenceDate(evidence.occurredAt)]
                  .filter(Boolean)
                  .join(' · ')}
              </Text>
            </View>
          ))
        ) : (
          <Text style={styles.nodeCopy}>Подтверждений пока нет</Text>
        )}
      </JourneyNode>

      <View style={styles.openRow}>
        <Text style={styles.openLabel}>Открыть цель</Text>
        <Text accessibilityElementsHidden style={styles.openArrow}>
          →
        </Text>
      </View>
    </Pressable>
  );
}

function ProgressReveal({
  label,
  reduceMotion,
}: {
  label: string;
  reduceMotion: boolean;
}) {
  const opacity = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    opacity.stopAnimation();
    if (reduceMotion) {
      opacity.setValue(1);
      return;
    }
    opacity.setValue(0.25);
    const animation = Animated.timing(opacity, {
      toValue: 1,
      duration: motion.settle,
      useNativeDriver: true,
    });
    animation.start();
    return () => animation.stop();
  }, [label, opacity, reduceMotion]);

  return (
    <Animated.Text style={[styles.progress, { opacity }]}>
      {label}
    </Animated.Text>
  );
}

function JourneyNode({
  children,
  marker,
}: {
  children: ReactNode;
  marker: 'goal' | 'regular' | 'current' | 'completed' | 'quiet';
}) {
  return (
    <View style={styles.node}>
      <View
        accessibilityElementsHidden
        style={[
          styles.marker,
          marker === 'goal' && styles.goalMarker,
          marker === 'current' && styles.currentMarker,
          marker === 'completed' && styles.completedMarker,
          marker === 'quiet' && styles.quietMarker,
        ]}
      />
      <View style={styles.nodeContent}>{children}</View>
    </View>
  );
}

function formatEvidenceDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(date);
}

const styles = StyleSheet.create({
  pressable: {
    position: 'relative',
    paddingVertical: spacing.xs,
    paddingRight: spacing.xs,
    borderRadius: radius.control,
  },
  pressed: { backgroundColor: colors.softBurgundy },
  line: {
    position: 'absolute',
    top: 17,
    bottom: 29,
    left: 7,
    width: 2,
    backgroundColor: colors.burgundy,
    opacity: 0.58,
  },
  node: {
    minHeight: spacing.touch,
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  marker: {
    width: 10,
    height: 10,
    marginTop: 6,
    marginLeft: 3,
    borderRadius: radius.round,
    borderWidth: 2,
    borderColor: colors.burgundy,
    backgroundColor: colors.paper,
    zIndex: 1,
  },
  goalMarker: {
    width: 14,
    height: 14,
    marginTop: 3,
    marginLeft: 1,
    backgroundColor: colors.burgundy,
  },
  currentMarker: { backgroundColor: colors.burgundy },
  completedMarker: { backgroundColor: colors.burgundy },
  quietMarker: { borderColor: colors.rule, backgroundColor: colors.paper },
  nodeContent: {
    flex: 1,
    minWidth: 0,
    paddingLeft: spacing.md,
    paddingBottom: spacing.lg,
  },
  goalHeading: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
  },
  goalTitle: { ...typography.currentTitle, color: colors.ink, flex: 1 },
  progress: {
    ...typography.rowTitle,
    ...typography.tabular,
    color: colors.burgundy,
    flexShrink: 0,
  },
  formula: {
    ...typography.caption,
    color: colors.muted,
    marginTop: spacing.xs,
    maxWidth: 320,
  },
  nodeEyebrow: {
    ...typography.caption,
    color: colors.burgundy,
    textTransform: 'uppercase',
    letterSpacing: 0.35,
  },
  nodeTitle: { ...typography.rowTitle, color: colors.ink, marginTop: 2 },
  nodeCopy: { ...typography.body, color: colors.muted, marginTop: 2 },
  evidenceRow: {
    paddingTop: spacing.xs,
    paddingBottom: spacing.xxs,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.rule,
  },
  openRow: {
    minHeight: spacing.touch,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginLeft: 26,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.rule,
  },
  openLabel: { ...typography.bodyMedium, color: colors.burgundy },
  openArrow: { ...typography.body, color: colors.burgundy },
});
