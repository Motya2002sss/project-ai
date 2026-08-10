import { StyleSheet, Text, View } from 'react-native';

import { colors } from '../../theme/colors';
import { spacing } from '../../theme/spacing';
import { typography } from '../../theme/typography';

export function ProcessingNotice({ slow }: { slow: boolean }) {
  return (
    <View accessibilityLiveRegion="polite" style={styles.notice}>
      <Text style={styles.title}>Пересобираю день…</Text>
      {slow ? (
        <Text style={styles.copy}>
          Это занимает чуть дольше обычного. Текст сохранён.
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  notice: {
    marginTop: spacing.md,
    paddingVertical: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: colors.rule,
  },
  title: { ...typography.bodyMedium, color: colors.burgundy },
  copy: { ...typography.body, color: colors.muted, marginTop: spacing.xxs },
});
