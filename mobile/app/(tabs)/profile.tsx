import { useRouter } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { usePlanner } from '../../src/features/planner/PlannerProvider';
import { colors } from '../../src/theme/colors';
import { radius } from '../../src/theme/radius';
import { spacing } from '../../src/theme/spacing';
import { typography } from '../../src/theme/typography';

export default function ProfileRoute() {
  const router = useRouter();
  const { apiBaseUrl } = usePlanner();
  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.content}>
        <Text accessibilityRole="header" style={styles.title}>
          Профиль
        </Text>
        <Text style={styles.caption}>Локальный dogfooding</Text>
        <Pressable
          accessibilityRole="button"
          onPress={() => router.push('/setup')}
          style={({ pressed }) => [styles.row, pressed && styles.pressed]}
        >
          <View style={styles.rowCopy}>
            <Text style={styles.rowTitle}>Доступ к backend</Text>
            <Text numberOfLines={2} style={styles.rowDetail}>
              {apiBaseUrl || 'Base URL не задан'}
            </Text>
          </View>
          <Text style={styles.arrow}>›</Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: colors.paper },
  content: { flex: 1, padding: spacing.screen, paddingTop: spacing.md },
  title: { ...typography.screenTitle, color: colors.ink },
  caption: {
    ...typography.caption,
    color: colors.burgundy,
    textTransform: 'uppercase',
    letterSpacing: 0.4,
    marginTop: 52,
  },
  row: {
    minHeight: 72,
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: spacing.sm,
    paddingVertical: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: colors.rule,
    borderRadius: radius.control,
  },
  rowCopy: { flex: 1 },
  rowTitle: { ...typography.bodyMedium, color: colors.ink },
  rowDetail: { ...typography.body, color: colors.muted, marginTop: spacing.xxs },
  arrow: { fontSize: 28, color: colors.muted, paddingHorizontal: spacing.xs },
  pressed: { backgroundColor: colors.softBurgundy },
});
