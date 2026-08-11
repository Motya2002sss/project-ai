import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    reason: str | None = None
    safe_message: str | None = None


_EATING_DISORDER = re.compile(
    r"\b(анорекси\w*|булими\w*|расстройств\w*\s+пищев\w*\s+поведен\w*|"
    r"eating\s+disorder)\b"
)
_EXTREME_RESTRICTION = re.compile(
    r"\b(голодат\w*|почти\s+не\s+ест\w*|совсем\s+не\s+ест\w*|"
    r"не\s+есть\s+(?:всю\s+)?недел\w*|сух\w*\s+голодан\w*)\b"
)
_VERY_LOW_CALORIES = re.compile(r"\b(?:[1-7]\d{2}|\d{1,2})\s*(?:ккал|калори\w*)\b")
_MEDICAL_TREATMENT = re.compile(
    r"\b(диагностир\w*|назнач\w*\s+лечен\w*|лечи(?:ть|\s+меня)|"
    r"подбер\w*\s+(?:лекарств\w*|препарат\w*)|дозировк\w*\s+лекарств\w*)\b"
)
_ONE_REP_MAX = re.compile(r"\b(?:1\s*(?:rm|пм)|одноповтор\w*\s+максим\w*)\b")
_ESCALATION = re.compile(r"\b(?:увелич\w*|подн\w*|добав\w*|прибав\w*|максим\w*)\b")
_INJURY = re.compile(r"\b(?:травм\w*|поврежден\w*|растяжен\w*|перелом\w*)\b")
_PAIN = re.compile(r"\b(?:болит\w*|больно\w*|через\s+боль|остр\w*\s+боль)\b")
_LOAD_REQUEST = re.compile(
    r"\b(?:нагруз\w*|трениров\w*|упражнен\w*|вес\w*|повтор\w*)\b"
)
_ALLERGY = re.compile(r"\b(?:аллерги\w*|анафилакс\w*|непереносимост\w*)\b")
_FOOD_GENERATION = re.compile(
    r"\b(?:сгенерир\w*|состав\w*|подбер\w*)\b.*\b(?:меню|рацион|ед\w*)\b"
)


def evaluate_activity_safety(text: str) -> SafetyDecision:
    normalized = " ".join(text.casefold().split())

    if _EATING_DISORDER.search(normalized):
        return SafetyDecision(
            allowed=False,
            reason="eating_disorder",
            safe_message=(
                "Я не буду составлять ограничительный план питания в этой ситуации. "
                "Безопаснее обсудить питание с профильным специалистом."
            ),
        )
    if _EXTREME_RESTRICTION.search(normalized) or _VERY_LOW_CALORIES.search(
        normalized
    ):
        return SafetyDecision(
            allowed=False,
            reason="extreme_restriction",
            safe_message=(
                "Я не буду планировать экстремальное ограничение питания. "
                "Можно зафиксировать обычный режим и обратиться к профильному специалисту."
            ),
        )
    if _MEDICAL_TREATMENT.search(normalized):
        return SafetyDecision(
            allowed=False,
            reason="medical_diagnosis_or_treatment",
            safe_message=(
                "Я не могу назначать лечение. Обратитесь к квалифицированному "
                "медицинскому специалисту."
            ),
        )
    if _ONE_REP_MAX.search(normalized) and _ESCALATION.search(normalized):
        return SafetyDecision(
            allowed=False,
            reason="unsafe_one_rep_max",
            safe_message=(
                "Я не буду автоматически повышать предельный вес. "
                "Такую нагрузку стоит согласовать с квалифицированным тренером."
            ),
        )
    if (_INJURY.search(normalized) or _PAIN.search(normalized)) and _LOAD_REQUEST.search(
        normalized
    ):
        return SafetyDecision(
            allowed=False,
            reason="injury_limitation",
            safe_message=(
                "Я не буду подбирать нагрузку через боль или после травмы. "
                "Сначала получите рекомендации подходящего специалиста."
            ),
        )
    if _ALLERGY.search(normalized) and _FOOD_GENERATION.search(normalized):
        return SafetyDecision(
            allowed=False,
            reason="allergy_risk",
            safe_message=(
                "Я не могу гарантировать безопасность меню при аллергии. "
                "Проверьте состав продуктов и обсудите рацион со специалистом."
            ),
        )
    return SafetyDecision(allowed=True)
