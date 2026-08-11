import { useRouter } from 'expo-router';
import { useMemo } from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { usePlanner } from '../../src/features/planner/PlannerProvider';
import { buildPathModel } from '../../src/features/path/pathModel';
import { colors } from '../../src/theme/colors';
import { radius } from '../../src/theme/radius';
import { spacing } from '../../src/theme/spacing';
import { typography } from '../../src/theme/typography';

export default function PathRoute() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const { openCapture, state } = usePlanner();
  const gutter = width <= 375 ? spacing.screenNarrow : spacing.screen;
  const pathModel = useMemo(
    () => buildPathModel(state.today.snapshot?.goals ?? []),
    [state.today.snapshot?.goals],
  );

  const describeGoal = () => {
    openCapture();
    router.replace('/');
  };

  return (
    <SafeAreaView edges={['top']} style={styles.safeArea}>
      <ScrollView
        contentContainerStyle={[styles.content, { paddingHorizontal: gutter }]}
      >
        <Text accessibilityRole="header" style={styles.title}>
          Путь
        </Text>

        {pathModel.state === 'ready' ? (
          <View style={styles.readyState}>
            <Text style={styles.eyebrow}>Активные цели</Text>
            <View style={styles.goals}>
              {pathModel.goals.map((goal) => (
                <View key={goal.id} style={styles.goalRow}>
                  <View accessibilityElementsHidden style={styles.goalMarker} />
                  <Text style={styles.goalTitle}>{goal.title}</Text>
                </View>
              ))}
            </View>
            <Text style={styles.readyCopy}>
              Сейчас здесь доступны только активные цели. Прогресс пока не
              рассчитывается.
            </Text>
            <Pressable
              accessibilityRole="button"
              onPress={describeGoal}
              style={({ pressed }) => [
                styles.textAction,
                pressed && styles.actionPressed,
              ]}
            >
              <Text style={styles.textActionLabel}>Сообщить об изменении</Text>
            </Pressable>
          </View>
        ) : (
          <View style={styles.emptyState}>
            <View accessibilityElementsHidden style={styles.progressSeed}>
              <View style={styles.marker} />
              <View style={styles.line} />
            </View>
            <Text style={styles.eyebrow}>Долгосрочный маршрут</Text>
            <Text style={styles.messageTitle}>С чего хотите начать?</Text>
            <Text style={styles.copy}>
              Расскажите о цели обычными словами. Здесь появится только
              подтверждённый прогресс по реальным действиям.
            </Text>
            <Pressable
              accessibilityRole="button"
              onPress={describeGoal}
              style={({ pressed }) => [
                styles.action,
                pressed && styles.actionPressed,
              ]}
            >
              <Text style={styles.actionText}>Рассказать о цели</Text>
              <Text accessibilityElementsHidden style={styles.actionArrow}>
                →
              </Text>
            </Pressable>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: colors.paper },
  content: {
    flexGrow: 1,
    paddingTop: spacing.md,
    paddingBottom: spacing.xl,
  },
  title: { ...typography.screenTitle, color: colors.ink },
  emptyState: { maxWidth: 336, marginTop: 56 },
  readyState: { marginTop: 48 },
  progressSeed: {
    height: 12,
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  marker: {
    width: 9,
    height: 9,
    borderRadius: radius.round,
    backgroundColor: colors.burgundy,
  },
  line: {
    flex: 1,
    height: StyleSheet.hairlineWidth,
    marginLeft: spacing.xs,
    backgroundColor: colors.rule,
  },
  eyebrow: {
    ...typography.caption,
    color: colors.burgundy,
    textTransform: 'uppercase',
    letterSpacing: 0.4,
  },
  messageTitle: {
    ...typography.currentTitle,
    color: colors.ink,
    marginTop: spacing.xs,
  },
  copy: {
    ...typography.body,
    color: colors.muted,
    marginTop: spacing.sm,
  },
  action: {
    minHeight: 48,
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginTop: spacing.xl,
    paddingHorizontal: spacing.md,
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: radius.control,
  },
  actionPressed: { backgroundColor: colors.softBurgundy },
  actionText: { ...typography.bodyMedium, color: colors.ink },
  actionArrow: { ...typography.body, color: colors.burgundy },
  goals: {
    marginTop: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.rule,
  },
  goalRow: {
    minHeight: 68,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.rule,
  },
  goalMarker: {
    width: 9,
    height: 9,
    borderRadius: radius.round,
    backgroundColor: colors.burgundy,
  },
  goalTitle: { ...typography.rowTitle, color: colors.ink, flex: 1 },
  readyCopy: {
    ...typography.body,
    color: colors.muted,
    maxWidth: 336,
    marginTop: spacing.lg,
  },
  textAction: {
    minHeight: spacing.touch,
    alignSelf: 'flex-start',
    justifyContent: 'center',
    marginTop: spacing.md,
    borderRadius: radius.control,
  },
  textActionLabel: { ...typography.bodyMedium, color: colors.burgundy },
});
