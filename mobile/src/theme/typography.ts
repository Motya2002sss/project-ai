import type { TextStyle } from 'react-native';

export const typography = {
  caption: { fontSize: 12, lineHeight: 16, fontWeight: '400' },
  body: { fontSize: 15, lineHeight: 21, fontWeight: '400' },
  bodyMedium: { fontSize: 15, lineHeight: 21, fontWeight: '500' },
  rowTitle: { fontSize: 17, lineHeight: 22, fontWeight: '500' },
  currentTitle: { fontSize: 23, lineHeight: 28, fontWeight: '500' },
  sectionTitle: { fontSize: 17, lineHeight: 22, fontWeight: '500' },
  screenTitle: {
    fontSize: 34,
    lineHeight: 40,
    fontWeight: '500',
    letterSpacing: -1.1,
  },
  detailTitle: {
    fontSize: 34,
    lineHeight: 40,
    fontWeight: '500',
    letterSpacing: -0.9,
  },
  tabular: { fontVariant: ['tabular-nums'] },
} satisfies Record<string, TextStyle>;
