import { useLocalSearchParams, useRouter } from 'expo-router';
import { useMemo, type ReactNode } from 'react';
import {
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { colors } from '../../theme/colors';
import { radius } from '../../theme/radius';
import { spacing } from '../../theme/spacing';
import { typography } from '../../theme/typography';
import {
  buildGoalDetailsModel,
  type EvidenceModel,
  type GoalDetailsModel,
  type PathMilestoneModel,
} from './pathModel';
import { useGoalDetailsData } from './usePathData';

export function GoalDetailsScreen() {
  const params = useLocalSearchParams<{ id?: string }>();
  const publicId = typeof params.id === 'string' ? params.id : null;
  const router = useRouter();
  const { width } = useWindowDimensions();
  const { state, refresh, loadMoreEvidence, canRefresh } =
    useGoalDetailsData(publicId);
  const gutter = width <= 375 ? spacing.screenNarrow : spacing.screen;
  const model = useMemo(
    () =>
      state.detail
        ? buildGoalDetailsModel(state.detail, state.evidence, {
            cached: state.source === 'cache',
            hasMoreEvidence: state.nextCursor !== null,
          })
        : null,
    [state.detail, state.evidence, state.nextCursor, state.source],
  );
  const refreshing = state.status === 'loading' && model !== null;

  return (
    <SafeAreaView edges={['top', 'bottom']} style={styles.safeArea}>
      <View style={[styles.topBar, { paddingHorizontal: gutter }]}>
        <Pressable
          accessibilityLabel="Назад к пути"
          accessibilityRole="button"
          onPress={() =>
            router.canGoBack() ? router.back() : router.replace('/path')
          }
          style={({ pressed }) => [
            styles.back,
            pressed && styles.controlPressed,
          ]}
        >
          <Text accessibilityElementsHidden style={styles.backIcon}>
            ‹
          </Text>
        </Pressable>
        <Text style={styles.topBarTitle}>Цель</Text>
      </View>

      {!model && state.status === 'loading' ? (
        <GoalState
          eyebrow="Синхронизация"
          message="Загружаю подтверждённый путь цели…"
        />
      ) : null}
      {!model && state.status === 'error' ? (
        <GoalState
          canRetry={canRefresh}
          eyebrow="Цель недоступна"
          message={state.errorMessage ?? 'Не удалось загрузить цель.'}
          onRetry={() => void refresh()}
        />
      ) : null}
      {model ? (
        <ScrollView
          contentContainerStyle={[
            styles.content,
            { paddingHorizontal: gutter },
          ]}
          refreshControl={
            canRefresh ? (
              <RefreshControl
                onRefresh={() => void refresh()}
                refreshing={refreshing}
                tintColor={colors.burgundy}
              />
            ) : undefined
          }
        >
          <GoalDetailsContent
            evidenceError={state.evidenceError}
            evidenceLoading={
              state.evidenceStatus === 'loading' ||
              state.evidenceStatus === 'loadingMore'
            }
            model={model}
            onLoadMore={() => void loadMoreEvidence()}
            staleMessage={
              state.source === 'cache'
                ? state.status === 'error'
                  ? 'Сохранено на устройстве · не удалось обновить'
                  : 'Сохранено на устройстве'
                : state.status === 'error'
                  ? 'Не удалось обновить · показаны последние данные'
                  : null
            }
          />
        </ScrollView>
      ) : null}
    </SafeAreaView>
  );
}

function GoalDetailsContent({
  evidenceError,
  evidenceLoading,
  model,
  onLoadMore,
  staleMessage,
}: {
  evidenceError: string | null;
  evidenceLoading: boolean;
  model: GoalDetailsModel;
  onLoadMore: () => void;
  staleMessage: string | null;
}) {
  return (
    <>
      {staleMessage ? (
        <Text accessibilityLiveRegion="polite" style={styles.cacheNotice}>
          {staleMessage}
        </Text>
      ) : null}
      <Text style={styles.eyebrow}>{model.statusLabel}</Text>
      <Text accessibilityRole="header" style={styles.title}>
        {model.title}
      </Text>

      <View
        accessible
        accessibilityLabel={`${model.title}. ${model.percentage === null ? model.progressLabel : `Прогресс ${model.percentage} процентов`}. ${model.progressExplanation}`}
        style={styles.progressBlock}
      >
        <Text style={styles.progressValue}>{model.progressLabel}</Text>
        <Text style={styles.progressFormula}>{model.progressExplanation}</Text>
        {model.progressReason ? (
          <Text style={styles.progressReason}>
            {progressReasonLabel(model.progressReason)}
          </Text>
        ) : null}
      </View>

      <DetailSection title="Основание цели">
        <FactRow label="Статус" value={model.statusLabel} />
        <FactRow label="Область" value={lifeAreaLabel(model.lifeArea)} />
        <FactRow label="Модель прогресса" value={model.outcomeLabel} />
        <FactRow label="Срок" value={formatDate(model.deadline)} />
        <FactRow label="Нагрузка" value={model.allocation} />
        <FactRow label="Интенсивность" value={model.intensity} />
        <FactRow label="Исходное значение" value={model.baseline} />
        <FactRow label="Текущее значение" value={model.currentValue} />
        <FactRow label="Целевое значение" value={model.target} />
        <FactRow
          label="Прогноз"
          value={formatDate(model.forecastDate)}
        />
        <FactRow
          label="Уверенность данных"
          value={confidenceLabel(model.confidence)}
        />
      </DetailSection>

      {model.program ? (
        <DetailSection title="Текущая программа">
          <Text style={styles.sectionLead}>{model.program.name}</Text>
          <FactRow label="Минимум" value={model.program.minimum} />
          <FactRow label="Комфортно" value={model.program.comfortable} />
          <FactRow label="Максимум" value={model.program.maximum} />
        </DetailSection>
      ) : null}

      <DetailSection title="Маршрут">
        <GoalRoute
          currentPhase={model.currentPhase}
          milestones={model.milestones}
          nextStep={model.nextStep}
        />
      </DetailSection>

      <DetailSection title="Подтверждения">
        {model.evidence.length > 0 ? (
          <View>
            {model.evidence.map((item) => (
              <EvidenceRow evidence={item} key={item.id} />
            ))}
          </View>
        ) : evidenceLoading ? (
          <Text accessibilityLiveRegion="polite" style={styles.emptyCopy}>
            Загружаю историю…
          </Text>
        ) : (
          <Text style={styles.emptyCopy}>Подтверждений пока нет.</Text>
        )}
        {evidenceError ? (
          <Text accessibilityLiveRegion="polite" style={styles.inlineError}>
            {evidenceError}
          </Text>
        ) : null}
        {model.hasMoreEvidence ? (
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ busy: evidenceLoading }}
            disabled={evidenceLoading}
            onPress={onLoadMore}
            style={({ pressed }) => [
              styles.loadMore,
              pressed && styles.controlPressed,
              evidenceLoading && styles.disabled,
            ]}
          >
            <Text style={styles.loadMoreLabel}>
              {evidenceLoading ? 'Загружаю…' : 'Показать более ранние'}
            </Text>
          </Pressable>
        ) : null}
      </DetailSection>
    </>
  );
}

function GoalRoute({
  currentPhase,
  milestones,
  nextStep,
}: Pick<GoalDetailsModel, 'currentPhase' | 'milestones' | 'nextStep'>) {
  return (
    <View style={styles.route}>
      <View accessibilityElementsHidden style={styles.routeLine} />
      {milestones.length > 0 ? (
        milestones.map((milestone) => (
          <GoalRouteNode key={milestone.id} milestone={milestone} />
        ))
      ) : (
        <RouteNode eyebrow="Этапы" title="Этапы пока не определены" />
      )}
      <RouteNode
        active={Boolean(currentPhase)}
        copy={currentPhase?.programName ?? currentPhase?.dateRange ?? null}
        eyebrow="Текущая фаза"
        title={currentPhase?.title ?? 'Фаза пока не определена'}
      />
      <RouteNode
        active={Boolean(nextStep)}
        copy={nextStep?.detail ?? null}
        eyebrow="Следующий шаг"
        title={nextStep?.title ?? 'Следующий шаг пока не определён'}
      />
    </View>
  );
}

function GoalRouteNode({ milestone }: { milestone: PathMilestoneModel }) {
  return (
    <RouteNode
      active={milestone.status === 'active'}
      completed={milestone.status === 'completed'}
      copy={milestone.description}
      eyebrow={milestone.statusLabel}
      title={milestone.title}
    />
  );
}

function RouteNode({
  active = false,
  completed = false,
  copy,
  eyebrow,
  title,
}: {
  active?: boolean;
  completed?: boolean;
  copy?: string | null;
  eyebrow: string;
  title: string;
}) {
  return (
    <View style={styles.routeNode}>
      <View
        accessibilityElementsHidden
        style={[
          styles.routeMarker,
          (active || completed) && styles.routeMarkerFilled,
        ]}
      />
      <View style={styles.routeCopy}>
        <Text style={styles.routeEyebrow}>{eyebrow}</Text>
        <Text style={styles.routeTitle}>{title}</Text>
        {copy ? <Text style={styles.routeBody}>{copy}</Text> : null}
      </View>
    </View>
  );
}

function DetailSection({
  children,
  title,
}: {
  children: ReactNode;
  title: string;
}) {
  return (
    <View style={styles.section}>
      <Text accessibilityRole="header" style={styles.sectionTitle}>
        {title}
      </Text>
      <View style={styles.sectionBody}>{children}</View>
    </View>
  );
}

function FactRow({
  label,
  value,
}: {
  label: string;
  value: string | null;
}) {
  if (!value) return null;
  return (
    <View style={styles.factRow}>
      <Text style={styles.factLabel}>{label}</Text>
      <Text style={styles.factValue}>{value}</Text>
    </View>
  );
}

function EvidenceRow({ evidence }: { evidence: EvidenceModel }) {
  return (
    <View style={styles.evidenceRow}>
      <View style={styles.evidenceHeader}>
        <Text style={styles.evidenceTitle}>{evidence.typeLabel}</Text>
        <Text style={styles.evidenceDate}>
          {formatEvidenceDate(evidence.occurredAt)}
        </Text>
      </View>
      {evidence.value ? (
        <Text style={styles.evidenceValue}>{evidence.value}</Text>
      ) : null}
    </View>
  );
}

function GoalState({
  canRetry = false,
  eyebrow,
  message,
  onRetry,
}: {
  canRetry?: boolean;
  eyebrow: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <View style={styles.fullState}>
      <Text style={styles.eyebrow}>{eyebrow}</Text>
      <Text accessibilityLiveRegion="polite" style={styles.stateTitle}>
        {message}
      </Text>
      {canRetry && onRetry ? (
        <Pressable
          accessibilityRole="button"
          onPress={onRetry}
          style={({ pressed }) => [
            styles.retry,
            pressed && styles.controlPressed,
          ]}
        >
          <Text style={styles.loadMoreLabel}>Повторить</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

function formatDate(value: string | null): string | null {
  if (!value) return null;
  const [year, month, day] = value.slice(0, 10).split('-').map(Number);
  if (!year || !month || !day) return value;
  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(Date.UTC(year, month - 1, day)));
}

function formatEvidenceDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function confidenceLabel(value: string): string {
  if (value === 'high') return 'Высокая';
  if (value === 'medium') return 'Средняя';
  if (value === 'low') return 'Низкая';
  return value;
}

function lifeAreaLabel(value: string | null): string | null {
  if (value === 'body') return 'Тело и здоровье';
  if (value === 'career') return 'Карьера';
  if (value === 'learning') return 'Обучение';
  if (value === 'relationships') return 'Отношения';
  if (value === 'finance') return 'Финансы';
  if (value === 'home') return 'Дом';
  return value;
}

function progressReasonLabel(reason: string): string {
  if (reason === 'not_calculated') return 'Расчёт ещё не сохранён.';
  if (reason === 'insufficient_data') return 'Пока недостаточно данных.';
  if (reason === 'invalid_target') return 'Нужно уточнить параметры цели.';
  if (reason === 'invalid_milestone_weights') {
    return 'Нужно уточнить веса этапов.';
  }
  return reason;
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: colors.paper },
  topBar: {
    minHeight: 60,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.rule,
  },
  back: {
    width: spacing.touch,
    height: spacing.touch,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: radius.control,
  },
  backIcon: { fontSize: 30, lineHeight: 30, color: colors.ink },
  topBarTitle: { ...typography.bodyMedium, color: colors.ink },
  content: { paddingTop: 36, paddingBottom: 56 },
  cacheNotice: {
    ...typography.caption,
    color: colors.burgundy,
    marginBottom: spacing.md,
  },
  eyebrow: {
    ...typography.caption,
    color: colors.burgundy,
    textTransform: 'uppercase',
    letterSpacing: 0.4,
  },
  title: {
    ...typography.detailTitle,
    color: colors.ink,
    maxWidth: 350,
    marginTop: spacing.xs,
  },
  progressBlock: {
    marginTop: spacing.xl,
    paddingLeft: spacing.md,
    paddingVertical: spacing.xs,
    borderLeftWidth: 2,
    borderLeftColor: colors.burgundy,
  },
  progressValue: {
    ...typography.currentTitle,
    ...typography.tabular,
    color: colors.burgundy,
  },
  progressFormula: {
    ...typography.body,
    color: colors.ink,
    maxWidth: 320,
    marginTop: spacing.xs,
  },
  progressReason: {
    ...typography.caption,
    color: colors.muted,
    marginTop: spacing.xxs,
  },
  section: {
    marginTop: 36,
    paddingTop: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.rule,
  },
  sectionTitle: { ...typography.sectionTitle, color: colors.ink },
  sectionBody: { marginTop: spacing.sm },
  sectionLead: {
    ...typography.rowTitle,
    color: colors.ink,
    marginBottom: spacing.xs,
  },
  factRow: {
    minHeight: spacing.touch,
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
    gap: spacing.md,
    paddingVertical: spacing.xs,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.rule,
  },
  factLabel: { ...typography.body, color: colors.muted, flex: 1 },
  factValue: {
    ...typography.bodyMedium,
    ...typography.tabular,
    color: colors.ink,
    flex: 1,
    textAlign: 'right',
  },
  route: { position: 'relative' },
  routeLine: {
    position: 'absolute',
    top: 8,
    bottom: 30,
    left: 5,
    width: 2,
    backgroundColor: colors.burgundy,
    opacity: 0.58,
  },
  routeNode: {
    minHeight: spacing.touch,
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  routeMarker: {
    width: 11,
    height: 11,
    marginTop: 6,
    borderRadius: radius.round,
    borderWidth: 2,
    borderColor: colors.rule,
    backgroundColor: colors.paper,
    zIndex: 1,
  },
  routeMarkerFilled: {
    borderColor: colors.burgundy,
    backgroundColor: colors.burgundy,
  },
  routeCopy: { flex: 1, minWidth: 0, paddingLeft: spacing.md, paddingBottom: spacing.lg },
  routeEyebrow: {
    ...typography.caption,
    color: colors.burgundy,
    textTransform: 'uppercase',
    letterSpacing: 0.35,
  },
  routeTitle: { ...typography.rowTitle, color: colors.ink, marginTop: 2 },
  routeBody: { ...typography.body, color: colors.muted, marginTop: 2 },
  evidenceRow: {
    minHeight: 58,
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.rule,
  },
  evidenceHeader: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  evidenceTitle: { ...typography.bodyMedium, color: colors.ink, flex: 1 },
  evidenceDate: {
    ...typography.caption,
    ...typography.tabular,
    color: colors.muted,
    flexShrink: 1,
    textAlign: 'right',
  },
  evidenceValue: {
    ...typography.body,
    ...typography.tabular,
    color: colors.muted,
    marginTop: spacing.xxs,
  },
  emptyCopy: { ...typography.body, color: colors.muted },
  inlineError: {
    ...typography.body,
    color: colors.burgundy,
    marginTop: spacing.sm,
  },
  loadMore: {
    minHeight: spacing.touch,
    alignSelf: 'flex-start',
    justifyContent: 'center',
    marginTop: spacing.sm,
    borderRadius: radius.control,
  },
  loadMoreLabel: { ...typography.bodyMedium, color: colors.burgundy },
  fullState: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: spacing.screen,
    paddingBottom: 80,
  },
  stateTitle: {
    ...typography.currentTitle,
    color: colors.ink,
    maxWidth: 336,
    marginTop: spacing.xs,
  },
  retry: {
    minHeight: spacing.touch,
    alignSelf: 'flex-start',
    justifyContent: 'center',
    marginTop: spacing.lg,
    paddingHorizontal: spacing.md,
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: radius.control,
  },
  controlPressed: { backgroundColor: colors.softBurgundy },
  disabled: { opacity: 0.45 },
});
