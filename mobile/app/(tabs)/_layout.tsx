import { Slot } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { AppBottomNavigation } from '../../src/components/AppBottomNavigation';
import { colors } from '../../src/theme/colors';

export default function TabsLayout() {
  return (
    <View style={styles.root}>
      <Slot />
      <AppBottomNavigation />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.paper },
});
