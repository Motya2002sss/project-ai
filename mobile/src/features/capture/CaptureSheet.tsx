import {
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useReduceMotion } from '../../accessibility/useReduceMotion';
import type { DaySnapshotDto } from '../../api/types';
import { colors } from '../../theme/colors';
import { modalAnimationType } from '../../theme/motion';
import { radius } from '../../theme/radius';
import { spacing } from '../../theme/spacing';
import { typography } from '../../theme/typography';
import { InteractionSheet } from '../interactions/InteractionSheet';
import type { CaptureState } from '../planner/plannerReducer';

interface CaptureSheetProps {
  capture: CaptureState;
  draft: string;
  snapshot: DaySnapshotDto | null;
  onChangeDraft: (value: string) => void;
  onClose: () => void;
  onSubmit: () => void;
  onRetry: () => void;
  onRespond: (interactionId: string, optionId?: string, text?: string) => void;
}

const interactionStates = new Set(['clarification', 'confirmation', 'conflict']);

export function CaptureSheet({
  capture,
  draft,
  snapshot,
  onChangeDraft,
  onClose,
  onSubmit,
  onRetry,
  onRespond,
}: CaptureSheetProps) {
  const insets = useSafeAreaInsets();
  const reduceMotion = useReduceMotion();
  const visible = !['idle', 'success'].includes(capture.status);
  const submitting = capture.status === 'submitting';
  const error = capture.status === 'error' ? capture : null;
  const interaction = interactionStates.has(capture.status)
    ? (capture as Extract<
        CaptureState,
        { status: 'clarification' | 'confirmation' | 'conflict' }
      >)
    : null;

  const handleClose = () => {
    if (!submitting) onClose();
  };

  return (
    <Modal
      animationType={modalAnimationType(reduceMotion)}
      onRequestClose={handleClose}
      transparent
      visible={visible}
    >
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.overlay}
      >
        <View style={[StyleSheet.absoluteFill, styles.inertBackdrop]} />
        <View style={styles.sheet}>
          <ScrollView
            bounces={false}
            contentContainerStyle={[
              styles.sheetContent,
              { paddingBottom: Math.max(insets.bottom, 16) },
            ]}
            keyboardDismissMode="interactive"
            keyboardShouldPersistTaps="handled"
            style={styles.scroller}
          >
            {interaction ? (
              <InteractionSheet
                capture={interaction}
                snapshot={snapshot}
                onClose={onClose}
                onRespond={onRespond}
              />
            ) : (
              <>
                <View style={styles.header}>
                  <View style={styles.headerCopy}>
                    <Text style={styles.eyebrow}>Быстрое изменение</Text>
                    <Text accessibilityRole="header" style={styles.title}>
                      Что изменилось?
                    </Text>
                  </View>
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel="Закрыть"
                    accessibilityState={{ disabled: submitting }}
                    disabled={submitting}
                    onPress={handleClose}
                    style={styles.close}
                  >
                    <Text style={styles.closeText}>×</Text>
                  </Pressable>
                </View>
                <TextInput
                  accessibilityLabel="Опишите изменение дня"
                  autoFocus={capture.status === 'editing'}
                  editable={!submitting}
                  maxLength={4000}
                  multiline
                  onChangeText={onChangeDraft}
                  placeholder="Например: сегодня задержусь на работе до 20"
                  placeholderTextColor={colors.muted}
                  style={styles.input}
                  textAlignVertical="top"
                  value={draft}
                />
                <Text style={styles.hint}>
                  {submitting
                    ? capture.slow
                      ? 'Это занимает чуть дольше обычного. Текст сохранён.'
                      : 'Пересобираю день…'
                    : error?.message ??
                      'Можно написать как обычно — расписание перестроится само.'}
                </Text>
                <Pressable
                  accessibilityRole="button"
                  accessibilityState={{
                    busy: submitting,
                    disabled: submitting || !draft.trim(),
                  }}
                  disabled={submitting || !draft.trim()}
                  onPress={error?.retryable ? onRetry : onSubmit}
                  style={[
                    styles.action,
                    (submitting || !draft.trim()) && styles.disabled,
                  ]}
                >
                  <Text style={styles.actionText}>
                    {submitting
                      ? 'Обновляю…'
                      : error?.retryable
                        ? 'Повторить'
                        : 'Обновить день'}
                  </Text>
                </Pressable>
              </>
            )}
          </ScrollView>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    justifyContent: 'flex-end',
    backgroundColor: colors.dim,
  },
  inertBackdrop: { pointerEvents: 'none' },
  sheet: {
    maxHeight: '92%',
    borderTopLeftRadius: radius.sheet,
    borderTopRightRadius: radius.sheet,
    backgroundColor: colors.raised,
    overflow: 'hidden',
  },
  scroller: { flexShrink: 1 },
  sheetContent: {
    paddingTop: spacing.lg,
    paddingHorizontal: spacing.screen,
  },
  header: {
    minHeight: spacing.touch,
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: spacing.md,
  },
  headerCopy: { flex: 1 },
  eyebrow: {
    ...typography.caption,
    color: colors.burgundy,
    textTransform: 'uppercase',
    letterSpacing: 0.4,
  },
  title: {
    ...typography.currentTitle,
    color: colors.ink,
    marginTop: spacing.xxs,
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
  input: {
    minHeight: 132,
    maxHeight: 260,
    marginTop: spacing.lg,
    padding: spacing.sm,
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: radius.input,
    backgroundColor: colors.raised,
    color: colors.ink,
    ...typography.body,
  },
  hint: { ...typography.body, color: colors.muted, marginTop: spacing.sm },
  action: {
    minHeight: spacing.touch,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: spacing.md,
    borderRadius: radius.control,
    backgroundColor: colors.ink,
  },
  actionText: { ...typography.bodyMedium, color: colors.paper },
  disabled: { opacity: 0.42 },
});
