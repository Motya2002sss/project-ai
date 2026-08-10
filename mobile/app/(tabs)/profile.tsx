import { useRouter } from 'expo-router';
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
import {
  buildProfileRows,
  type ProfileRowModel,
} from '../../src/features/shell/profileModel';
import { colors } from '../../src/theme/colors';
import { radius } from '../../src/theme/radius';
import { spacing } from '../../src/theme/spacing';
import { typography } from '../../src/theme/typography';

export default function ProfileRoute() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const { apiBaseUrl, state } = usePlanner();
  const gutter = width <= 375 ? spacing.screenNarrow : spacing.screen;
  const rows = buildProfileRows({
    apiConfigured: Boolean(apiBaseUrl),
    hasAuthoritativeToday: state.today.source === 'server',
    hasTodayError: Boolean(state.today.error),
  });

  const openRow = (row: ProfileRowModel) => {
    if (row.destination) router.push(row.destination);
  };

  return (
    <SafeAreaView edges={['top']} style={styles.safeArea}>
      <ScrollView
        contentContainerStyle={[styles.content, { paddingHorizontal: gutter }]}
      >
        <Text accessibilityRole="header" style={styles.title}>
          Профиль
        </Text>

        <View style={styles.identity}>
          <View accessibilityElementsHidden style={styles.avatar}>
            <Text style={styles.avatarText}>Л</Text>
          </View>
          <View style={styles.identityCopy}>
            <Text style={styles.identityTitle}>Локальный профиль</Text>
            <Text style={styles.identityDetail}>Dogfooding на этом устройстве</Text>
          </View>
        </View>

        <Text style={styles.caption}>Настройки</Text>
        <View style={styles.rows}>
          {rows.map((row) =>
            row.destination ? (
              <Pressable
                accessibilityRole="button"
                key={row.id}
                onPress={() => openRow(row)}
                style={({ pressed }) => [
                  styles.row,
                  pressed && styles.pressed,
                ]}
              >
                <View style={styles.rowCopy}>
                  <Text style={styles.rowTitle}>{row.title}</Text>
                  <Text style={styles.rowDetail}>{row.detail}</Text>
                </View>
                <Text accessibilityElementsHidden style={styles.arrow}>
                  ›
                </Text>
              </Pressable>
            ) : (
              <View
                accessible
                accessibilityLabel={`${row.title}. ${row.detail}. Позже`}
                key={row.id}
                style={[styles.row, styles.unavailableRow]}
              >
                <View style={styles.rowCopy}>
                  <Text style={styles.rowTitle}>{row.title}</Text>
                  <Text style={styles.rowDetail}>{row.detail}</Text>
                </View>
                <Text style={styles.later}>Позже</Text>
              </View>
            ),
          )}
        </View>
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
  identity: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 40,
  },
  avatar: {
    width: 48,
    height: 48,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.round,
    backgroundColor: colors.softBurgundy,
  },
  avatarText: {
    fontSize: 18,
    lineHeight: 22,
    fontWeight: '500',
    color: colors.burgundy,
  },
  identityCopy: { flex: 1, marginLeft: spacing.sm },
  identityTitle: { ...typography.rowTitle, color: colors.ink },
  identityDetail: {
    ...typography.body,
    color: colors.muted,
    marginTop: spacing.xxs,
  },
  caption: {
    ...typography.caption,
    color: colors.burgundy,
    textTransform: 'uppercase',
    letterSpacing: 0.4,
    marginTop: 40,
  },
  rows: {
    marginTop: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.rule,
  },
  row: {
    minHeight: 74,
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.rule,
  },
  rowCopy: { flex: 1 },
  rowTitle: { ...typography.bodyMedium, color: colors.ink },
  rowDetail: { ...typography.body, color: colors.muted, marginTop: spacing.xxs },
  arrow: {
    fontSize: 26,
    lineHeight: 30,
    color: colors.muted,
    marginLeft: spacing.sm,
    paddingHorizontal: spacing.xs,
  },
  unavailableRow: { opacity: 0.68 },
  later: {
    ...typography.caption,
    color: colors.muted,
    marginLeft: spacing.sm,
  },
  pressed: { backgroundColor: colors.softBurgundy },
});
