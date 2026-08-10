import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { colors } from '../../src/theme/colors';
import { spacing } from '../../src/theme/spacing';
import { typography } from '../../src/theme/typography';

export default function PathRoute() {
  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.content}>
        <Text accessibilityRole="header" style={styles.title}>
          Путь
        </Text>
        <View style={styles.message}>
          <Text style={styles.messageTitle}>Цели появятся здесь</Text>
          <Text style={styles.copy}>
            Здесь появится только подтверждённый прогресс по реальным действиям.
            Пока раздел не подключён.
          </Text>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: colors.paper },
  content: { flex: 1, padding: spacing.screen, paddingTop: spacing.md },
  title: { ...typography.screenTitle, color: colors.ink },
  message: { maxWidth: 310, marginTop: 64 },
  messageTitle: { ...typography.sectionTitle, color: colors.ink },
  copy: { ...typography.body, color: colors.muted, marginTop: spacing.xs },
});
