import { usePathname, useRouter } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors } from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';

const tabs = [
  {
    href: '/',
    label: 'Сегодня',
    match: (path: string) => path === '/' || path.startsWith('/dev/'),
  },
  { href: '/path', label: 'Путь', match: (path: string) => path === '/path' },
  {
    href: '/profile',
    label: 'Профиль',
    match: (path: string) => path === '/profile',
  },
] as const;

export function AppBottomNavigation() {
  const pathname = usePathname();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  return (
    <View
      accessibilityRole="tablist"
      style={[styles.navigation, { paddingBottom: Math.max(insets.bottom, 8) }]}
    >
      {tabs.map((tab) => {
        const selected = tab.match(pathname);
        return (
          <Pressable
            accessibilityRole="tab"
            accessibilityState={{ selected }}
            accessibilityLabel={tab.label}
            key={tab.href}
            onPress={() => router.replace(tab.href)}
            style={styles.tab}
          >
            <Text style={[styles.label, selected && styles.selectedLabel]}>
              {tab.label}
            </Text>
            <View style={[styles.dot, !selected && styles.hiddenDot]} />
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  navigation: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.rule,
    backgroundColor: colors.paper,
    paddingTop: spacing.xs,
  },
  tab: {
    minWidth: 88,
    minHeight: spacing.touch,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xxs,
  },
  label: { ...typography.body, color: colors.muted },
  selectedLabel: { ...typography.bodyMedium, color: colors.ink },
  dot: {
    width: 3,
    height: 3,
    borderRadius: 2,
    backgroundColor: colors.burgundy,
  },
  hiddenDot: { opacity: 0 },
});
