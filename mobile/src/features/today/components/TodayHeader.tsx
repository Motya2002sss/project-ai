import { StyleSheet, Text, View } from 'react-native';

import { colors } from '../../../theme/colors';
import { typography } from '../../../theme/typography';

interface TodayHeaderProps {
  dateLabel: string;
}

export function TodayHeader({ dateLabel }: TodayHeaderProps) {
  return (
    <View accessibilityRole="header" style={styles.header}>
      <Text style={styles.date}>{dateLabel}</Text>
      <Text style={styles.title}>Сегодня</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { alignItems: 'flex-start' },
  date: {
    ...typography.caption,
    color: colors.burgundy,
    letterSpacing: 0.4,
    textTransform: 'uppercase',
    marginBottom: 5,
  },
  title: { ...typography.screenTitle, color: colors.ink },
});
