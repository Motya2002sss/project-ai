import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import type { DaySnapshotDto, InteractionOptionDto } from '../../api/types';
import { colors } from '../../theme/colors';
import { radius } from '../../theme/radius';
import { spacing } from '../../theme/spacing';
import { typography } from '../../theme/typography';
import { mapPlanDiff } from '../capture/planDiffMapper';
import type { InteractionCaptureState } from '../planner/plannerReducer';

interface InteractionSheetProps {
  busy: boolean;
  capture: InteractionCaptureState;
  errorMessage: string | null;
  snapshot: DaySnapshotDto | null;
  onClose: () => void;
  onRespond: (interactionId: string, optionId?: string, text?: string) => void;
  onRetry?: () => void;
}

export function InteractionSheet({
  busy,
  capture,
  errorMessage,
  snapshot,
  onClose,
  onRespond,
  onRetry,
}: InteractionSheetProps) {
  const [answer, setAnswer] = useState('');
  let interactionId: string | null;
  let title: string;
  let summary: string | null;
  let options: InteractionOptionDto[];
  let freeTextAllowed: boolean;
  let diffLines: ReturnType<typeof mapPlanDiff> = [];
  let eyebrow: string;

  switch (capture.status) {
    case 'clarification':
      interactionId = capture.value.id;
      title = capture.value.question;
      summary = null;
      options = capture.value.options;
      freeTextAllowed = capture.value.free_text_allowed;
      eyebrow = 'Нужно уточнение';
      break;
    case 'confirmation':
      interactionId = capture.value.id;
      title = capture.value.title;
      summary = capture.value.summary;
      options = capture.value.options;
      freeTextAllowed = false;
      diffLines = snapshot ? mapPlanDiff(capture.value.changes, snapshot) : [];
      eyebrow = 'Перед изменением';
      break;
    case 'conflict':
      interactionId = capture.value.id;
      title = capture.value.title;
      summary = capture.value.message;
      options = capture.value.options;
      freeTextAllowed = Boolean(capture.value.id);
      eyebrow = 'Конфликт во времени';
      break;
  }

  useEffect(() => setAnswer(''), [interactionId]);

  const choose = (option: InteractionOptionDto) => {
    if (busy || !interactionId) return;
    onRespond(interactionId, option.id, option.value);
  };

  return (
    <View>
      <View style={styles.header}>
        <Text style={styles.eyebrow}>
          {eyebrow}
        </Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Закрыть"
          accessibilityState={{ disabled: busy }}
          disabled={busy}
          onPress={onClose}
          style={[styles.close, busy && styles.disabled]}
        >
          <Text style={styles.closeText}>×</Text>
        </Pressable>
      </View>
      <Text accessibilityRole="header" style={styles.title}>
        {title}
      </Text>
      {summary ? <Text style={styles.summary}>{summary}</Text> : null}
      {diffLines.map((line, index) => (
        <View key={`${line.title}-${index}`} style={styles.diffLine}>
          <Text style={styles.optionLabel}>{line.title}</Text>
          {line.detail ? <Text style={styles.optionValue}>{line.detail}</Text> : null}
        </View>
      ))}
      <View style={styles.options}>
        {options.map((option) => (
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ disabled: busy }}
            disabled={busy}
            key={option.id}
            onPress={() => choose(option)}
            style={({ pressed }) => [
              styles.option,
              pressed && !busy && styles.pressed,
              busy && styles.disabled,
            ]}
          >
            <Text style={styles.optionLabel}>{option.label}</Text>
          </Pressable>
        ))}
      </View>
      {freeTextAllowed ? (
        <View style={styles.freeText}>
          <TextInput
            accessibilityLabel="Ответить своими словами"
            editable={!busy}
            multiline
            onChangeText={setAnswer}
            placeholder="Ответить своими словами"
            placeholderTextColor={colors.muted}
            style={styles.input}
            value={answer}
          />
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ disabled: busy || !answer.trim() }}
            disabled={busy || !answer.trim()}
            onPress={() => onRespond(interactionId!, undefined, answer)}
            style={[
              styles.send,
              (busy || !answer.trim()) && styles.disabled,
            ]}
          >
            <Text style={styles.sendText}>
              {busy ? 'Отправляю…' : 'Ответить'}
            </Text>
          </Pressable>
        </View>
      ) : null}
      {busy && !freeTextAllowed ? (
        <Text accessibilityLiveRegion="polite" style={styles.status}>
          Отправляю ответ…
        </Text>
      ) : null}
      {errorMessage ? (
        <View style={styles.errorBlock}>
          <Text accessibilityLiveRegion="polite" style={styles.errorText}>
            {errorMessage}
          </Text>
          {onRetry ? (
            <Pressable
              accessibilityRole="button"
              onPress={onRetry}
              style={styles.retry}
            >
              <Text style={styles.retryText}>Повторить отправку</Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    minHeight: spacing.touch,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  eyebrow: {
    ...typography.caption,
    color: colors.burgundy,
    textTransform: 'uppercase',
    letterSpacing: 0.4,
  },
  close: {
    width: spacing.touch,
    height: spacing.touch,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: radius.control,
  },
  closeText: { fontSize: 24, lineHeight: 26, color: colors.muted },
  title: {
    ...typography.currentTitle,
    color: colors.ink,
    marginTop: spacing.sm,
  },
  summary: { ...typography.body, color: colors.muted, marginTop: spacing.sm },
  diffLine: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
    marginTop: spacing.xs,
  },
  options: { gap: spacing.xs, marginTop: spacing.lg },
  option: {
    minHeight: spacing.touch,
    justifyContent: 'center',
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: radius.control,
  },
  optionLabel: { ...typography.bodyMedium, color: colors.ink },
  optionValue: { ...typography.body, color: colors.muted },
  pressed: { backgroundColor: colors.softBurgundy },
  freeText: { marginTop: spacing.md },
  input: {
    minHeight: 88,
    maxHeight: 160,
    padding: spacing.sm,
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: radius.input,
    backgroundColor: colors.raised,
    color: colors.ink,
    textAlignVertical: 'top',
    ...typography.body,
  },
  send: {
    minHeight: spacing.touch,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: spacing.sm,
    borderRadius: radius.control,
    backgroundColor: colors.ink,
  },
  sendText: { ...typography.bodyMedium, color: colors.paper },
  status: { ...typography.body, color: colors.muted, marginTop: spacing.md },
  errorBlock: { marginTop: spacing.md },
  errorText: { ...typography.body, color: colors.burgundy },
  retry: {
    minHeight: spacing.touch,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: spacing.sm,
    borderWidth: 1,
    borderColor: colors.burgundy,
    borderRadius: radius.control,
  },
  retryText: { ...typography.bodyMedium, color: colors.burgundy },
  disabled: { opacity: 0.4 },
});
