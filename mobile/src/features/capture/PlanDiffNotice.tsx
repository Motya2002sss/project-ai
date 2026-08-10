import { StyleSheet, Text, View } from 'react-native';

import type { DaySnapshotDto, PlanDiffDto } from '../../api/types';
import { colors } from '../../theme/colors';
import { spacing } from '../../theme/spacing';
import { typography } from '../../theme/typography';
import { mapPlanDiff } from './planDiffMapper';

interface PlanDiffNoticeProps {
  diff: PlanDiffDto;
  snapshot: DaySnapshotDto;
  replyText: string;
  didChange: boolean;
}

export function PlanDiffNotice({
  diff,
  snapshot,
  replyText,
  didChange,
}: PlanDiffNoticeProps) {
  const lines = mapPlanDiff(diff, snapshot);
  return (
    <View accessibilityLiveRegion="polite" style={styles.notice}>
      <Text style={styles.heading}>
        {didChange ? 'План обновлён' : 'Без изменений'}
      </Text>
      {lines.length > 0 ? (
        lines.map((line, index) => (
          <View key={`${line.title}-${line.detail ?? ''}-${index}`} style={styles.line}>
            <Text style={styles.title}>{line.title}</Text>
            {line.detail ? <Text style={styles.detail}>{line.detail}</Text> : null}
          </View>
        ))
      ) : (
        <Text style={styles.detail}>{replyText}</Text>
      )}
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
  heading: { ...typography.bodyMedium, color: colors.burgundy },
  line: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'baseline',
    gap: spacing.xs,
    marginTop: spacing.xxs,
  },
  title: { ...typography.body, color: colors.ink },
  detail: { ...typography.body, ...typography.tabular, color: colors.muted },
});
