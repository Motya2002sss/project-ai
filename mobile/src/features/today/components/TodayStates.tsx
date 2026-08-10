import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors } from '../../../theme/colors';
import { radius } from '../../../theme/radius';
import { spacing } from '../../../theme/spacing';
import { typography } from '../../../theme/typography';

export function TodayLoadingState() {
  return (
    <View accessibilityLabel="Загружаю план дня" style={styles.loading}>
      <View style={[styles.skeleton, { width: '74%' }]} />
      <View style={[styles.skeleton, { width: '58%' }]} />
      <View style={[styles.skeleton, { width: '66%' }]} />
    </View>
  );
}

export function TodayErrorBanner({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <View accessibilityLiveRegion="polite" style={styles.banner}>
      <Text style={styles.bannerText}>{message}</Text>
      {onRetry ? (
        <Pressable accessibilityRole="button" onPress={onRetry} style={styles.retry}>
          <Text style={styles.retryText}>Повторить</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

export function TodayUnavailableState() {
  return (
    <View style={styles.centerState}>
      <Text style={styles.stateTitle}>План дня пока недоступен</Text>
      <Text style={styles.stateCopy}>Проверьте подключение и повторите загрузку.</Text>
    </View>
  );
}

export function EmptyDayState() {
  return (
    <View style={styles.centerState}>
      <Text style={styles.stateTitle}>День пока не собран</Text>
      <Text style={styles.stateCopy}>Расскажите, что сегодня важно или изменилось.</Text>
    </View>
  );
}

export function AllDoneState() {
  return (
    <View accessibilityLiveRegion="polite" style={styles.allDone}>
      <Text style={styles.stateTitle}>На сегодня всё</Text>
      <Text style={styles.stateCopy}>Свободное время остаётся вашим.</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  loading: { gap: spacing.lg, paddingTop: 38 },
  skeleton: {
    height: 54,
    borderRadius: radius.control,
    backgroundColor: colors.softBurgundy,
    opacity: 0.55,
  },
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
    minHeight: spacing.touch,
    marginTop: spacing.md,
    paddingVertical: spacing.xs,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: colors.rule,
  },
  bannerText: { ...typography.body, color: colors.muted, flex: 1 },
  retry: { minHeight: spacing.touch, justifyContent: 'center' },
  retryText: { ...typography.bodyMedium, color: colors.burgundy },
  centerState: { paddingVertical: 48, maxWidth: 280 },
  allDone: {
    marginTop: spacing.md,
    paddingTop: spacing.lg,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.rule,
  },
  stateTitle: { ...typography.sectionTitle, color: colors.ink },
  stateCopy: { ...typography.body, color: colors.muted, marginTop: spacing.xs },
});
