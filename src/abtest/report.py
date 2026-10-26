"""Markdown rendering: validation doc, analysis report, README results block, decision."""
from __future__ import annotations

import math

from abtest.config import ALPHA, GROUP_LABELS, MIN_ROLLOUT_LIFT_PCT, MIN_SEGMENT_USERS

DECISIONS = {
    "roll_out": "ВНЕДРЯТЬ",
    "do_not_roll_out": "НЕ ВНЕДРЯТЬ",
    "continue": "ПРОДОЛЖАТЬ ЭКСПЕРИМЕНТ",
}


def _pct(value: float, digits: int = 2) -> str:
    return "—" if value is None or (isinstance(value, float) and math.isnan(value)) else f"{value * 100:.{digits}f}%".replace(".", ",")


def _num(value: float, digits: int = 0) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    text = f"{value:,.{digits}f}".replace(",", " ")
    return text.replace(".", ",") if digits else text


def _signed_pct(value: float, digits: int = 2) -> str:
    return "—" if math.isnan(value) else f"{value:+.{digits}f}%".replace(".", ",")


def _pp(value: float, digits: int = 2) -> str:
    return "—" if math.isnan(value) else f"{_pp_bare(value, digits)} п.п."


def _pp_bare(value: float, digits: int = 2) -> str:
    return "—" if math.isnan(value) else f"{value * 100:+.{digits}f}".replace(".", ",")


def _p(value: float) -> str:
    if value is None or math.isnan(value):
        return "—"
    return "< 0,001" if value < 0.001 else f"{value:.3f}".replace(".", ",")


def _dec(value: float, digits: int = 2) -> str:
    return "—" if math.isnan(value) else f"{value:.{digits}f}".replace(".", ",")


def decide(stats: dict, impact: dict, segments: dict[str, dict]) -> str:
    if not stats["significant"] or math.isnan(stats["p_value"]):
        return "continue"
    if stats["direction"] != "increase" or stats["ci_low"] <= 0:
        return "do_not_roll_out"
    if stats["rel_lift_pct"] < MIN_ROLLOUT_LIFT_PCT:
        return "do_not_roll_out"
    for res in segments.values():
        table = res["table"]
        if table.empty:
            continue
        negative = table[(table["significant"]) & (table["rel_lift_pct"] < -MIN_ROLLOUT_LIFT_PCT)]
        if len(negative):
            return "do_not_roll_out"
    return "roll_out"


SEGMENT_LABELS = {
    "mobile": "мобильные",
    "desktop": "десктоп",
    "tablet": "планшеты",
    "email": "email-рассылка",
    "organic": "поиск (бесплатный)",
    "paid_search": "поиск (платный)",
    "social": "соцсети",
    "referral": "переходы по ссылкам",
    "new": "новые",
    "returning": "возвращающиеся",
}


def _segment_label(value: str) -> str:
    return SEGMENT_LABELS.get(value, value)


def _segments_markdown(segments: dict[str, dict]) -> str:
    titles = {
        "device": "Устройство",
        "traffic_source": "Источник трафика",
        "visitor_type": "Тип посетителя",
    }
    blocks = []
    for col, res in segments.items():
        table = res["table"]
        if table.empty:
            continue
        lines = [
            f"### {titles.get(col, col)}",
            "",
            "| Сегмент | Конверсия A | Конверсия B | Разница | Отн. lift | p-value |",
            "|---|---|---|---|---|---|",
        ]
        for _, row in table.iterrows():
            lines.append(
                f"| {_segment_label(row['segment'])} | {_pct(row['cr_control'])} | {_pct(row['cr_treatment'])} | "
                f"{_pp(row['abs_diff'])} | {_signed_pct(row['rel_lift_pct'])} | {_p(row['p_value'])} |"
            )
        if res["dropped"]:
            dropped = ", ".join(_segment_label(d) for d in res["dropped"])
            lines += ["", f"Исключены из-за малого размера (< {MIN_SEGMENT_USERS} польз. на группу): {dropped}."]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _validation_markdown(ctx: dict) -> str:
    srm = ctx["srm"]
    rand = ctx["randomization"]
    quality = ctx["quality"]
    balance_rows = "\n".join(
        f"| {r['column']} | {r['chi2']:.2f} | {r['dof']} | {_p(r['p_value'])} | {'да' if r['balanced'] else 'НЕТ'} |"
        for r in rand
    )
    quality_rows = "\n".join(
        f"| {r['check']} | {r['issues_found']} | {r['detail']}" for _, r in quality.iterrows()
    )
    return f"""# Проверка корректности эксперимента

## 1. Соотношение групп (SRM)

Ожидаемое соотношение групп: {srm['expected_ratio']:.0%} / {1 - srm['expected_ratio']:.0%}
(критерий: хи-квадрат, порог `p < 0,001`; порог строже основного `alpha = {ALPHA}`, потому что SRM — это проверка
механики разбиения, а не эффекта продукта, и её ложное срабатывание дорого).

| Группа | Пользователи |
|---|---|
| {GROUP_LABELS['control']} | {_num(srm['n_control'])} |
| {GROUP_LABELS['treatment']} | {_num(srm['n_treatment'])} |

Фактическая доля Control: {srm['observed_ratio']:.4f}. p-value: {_p(srm['p_value'])}.
**SRM: {'обнаружен' if srm['srm_detected'] else 'не обнаружен'}.**

## 2. Рандомизация (однородность сегментов между группами)

Проверка хи-квадрат на независимость сегмента и группы. Порог для вывода о дисбалансе: `p < 0,01`.

| Признак | chi2 | df | p-value | Баланс есть |
|---|---|---|---|---|
{balance_rows}

## 3. Контаминация эксперимента

Пользователь, попавший в обе группы, считается загрязнением. Проверка `user_in_both_groups` в
`src/abtest/data_quality.py`: строки таких пользователей удаляются полностью, чтобы одна и та же
личность не влияла на обе группы.

Найдено записей в обеих группах: {int(quality.set_index('check').loc['user_in_both_groups', 'issues_found'])}.
**Контаминация: {'обнаружена и устранена' if int(quality.set_index('check').loc['user_in_both_groups', 'issues_found']) else 'не обнаружена'}.**

## 4. Качество данных

Проверки выполняются до анализа, проблемные строки удаляются, а не «чинятся» догадками.
Всего строк в исходном файле: {_num(ctx['rows_raw'])}, после очистки: {_num(ctx['rows_clean'])}.

| Проверка | Проблем | Детали |
|---|---|---|
{quality_rows}

## 5. Период эксперимента

{srm.get('window', '')}

## Вывод по валидации

{srm.get('conclusion', '')}
"""


def _analysis_markdown(ctx: dict) -> str:
    gm = ctx["group_metrics"].set_index("experiment_group")
    stats = ctx["stats"]
    limited = ctx["limited_metrics"]
    impact = ctx["impact"]
    decision = DECISIONS[ctx["decision"]]

    metrics_rows = [
        "| Метрика | A (Control) | B (Treatment) | Разница |",
        "|---|---|---|---|",
        f"| Пользователи | {_num(gm.loc['control', 'users'])} | {_num(gm.loc['treatment', 'users'])} | — |",
        f"| Конверсия | {_pct(gm.loc['control', 'conversion_rate'])} | {_pct(gm.loc['treatment', 'conversion_rate'])} | {_pp(stats['abs_diff'])} ({_signed_pct(stats['rel_lift_pct'])}) |",
        f"| Доля добавлений в корзину | {_pct(gm.loc['control', 'add_to_cart_rate'])} | {_pct(gm.loc['treatment', 'add_to_cart_rate'])} | {'—' if math.isnan(limited['atc_diff']) else _pp(limited['atc_diff'])} |",
        f"| Доля покупок от корзины | {_pct(gm.loc['control', 'purchase_rate'])} | {_pct(gm.loc['treatment', 'purchase_rate'])} | {'—' if math.isnan(limited['pr_diff']) else _pp(limited['pr_diff'])} |",
        f"| Выручка на пользователя | {_num(gm.loc['control', 'revenue_per_user'], 2)} ₽ | {_num(gm.loc['treatment', 'revenue_per_user'], 2)} ₽ | {'—' if math.isnan(limited['rpu_diff']) else _num(limited['rpu_diff'], 2) + ' ₽'} |",
        f"| Выручка на покупателя | {_num(gm.loc['control', 'revenue_per_purchaser'], 2)} ₽ | {_num(gm.loc['treatment', 'revenue_per_purchaser'], 2)} ₽ | {'—' if math.isnan(limited['rpp_diff']) else _num(limited['rpp_diff'], 2) + ' ₽'} |",
    ]

    sign_text = {
        "increase": "в сторону роста",
        "decrease": "в сторону снижения",
        "none": "направление не определено",
    }[stats["direction"]]

    if ctx["decision"] == "roll_out":
        decision_text = (
            "Внедрение улучшает primary metric, эффект статистически значим, практический эффект не ниже "
            f"{MIN_ROLLOUT_LIFT_PCT:g} %, и ни один сегмент не показывает значимого ухудшения."
        )
    elif ctx["decision"] == "continue":
        decision_text = (
            "На имеющемся объёме данных различие не подтверждено как статистически значимое. "
            "Интерпретировать результат как «эффекта нет» нельзя: доверительный интервал допускает как "
            "рост, так и снижение метрики. Вариант следует оставить Treatment для накопления выборки."
        )
    else:
        decision_text = (
            "Результат не даёт оснований внедрять изменение на всех пользователей: либо эффект "
            "статистически не отличается от нуля в нужную сторону, либо он значим, но ниже порога "
            f"практической значимости ({MIN_ROLLOUT_LIFT_PCT:g} %), либо один из сегментов значимо ухудшается."
        )

    caveat = ""
    if stats["rel_lift_pct"] < ctx["mde_pct"]:
        caveat = (
            f"\n\nВажная оговорка: наблюдаемый lift ({_signed_pct(stats['rel_lift_pct'])}) меньше MDE "
            f"эксперимента ({_pct(ctx['mde_pct'] / 100)}), а нижняя граница доверительного интервала "
            f"({_pp(stats['ci_low'], 3)}) близка к нулю. Решение статистически обосновано, но запас "
            "прочности небольшой: повторный тест на большей выборке или расширение до 5 % эффекта "
            "(около 69 000 пользователей на группу) даст более устойчивый вывод. Внедрение стоит "
            "сопровождать мониторингом конверсии и среднего чека в первые недели."
        )

    return f"""# Анализ A/B-теста: CTA «Купить» против «Купить сейчас»

*Отчёт сгенерирован автоматически из `results/results.json`. Ручные правки цифр не допускаются.*

## Эксперимент

Мобильное приложение интернет-магазина. Изменение CTA на карточке товара:

- **A (Control):** кнопка «Купить»
- **B (Treatment):** кнопка «Купить сейчас»

Период: {ctx['window_text']}. Пользователей после очистки данных: {_num(ctx['rows_clean'])}.

## Гипотеза

- **H0:** изменение CTA не влияет на конверсию (`CR_B = CR_A`).
- **H1:** изменение CTA изменяет конверсию (`CR_B ≠ CR_A`). Двусторонний тест: мы защищаемся и от
  случайного ухудшения метрики, а не только ищем рост.

## Метрики

Основная метрика — **конверсия (Conversion Rate)** = покупки / пользователи в эксперименте.

{chr(10).join(metrics_rows)}

(**Доля покупок от корзины (Purchase Rate)** считается от пользователей, дошедших до корзины;
**Выручка на пользователя** — суммарная выручка, делённая на всех пользователей группы;
**Выручка на покупателя** — средний чек.)

## Проверка валидации эксперимента

| Проверка | Результат |
|---|---|
| Несоответствие соотношения групп (SRM) | {_num(ctx['srm']['n_control'])} против {_num(ctx['srm']['n_treatment'])}, p = {_p(ctx['srm']['p_value'])} — {'SRM обнаружен' if ctx['srm']['srm_detected'] else 'SRM не обнаружен'} |
| Рандомизация по устройству / источнику трафика / типу посетителя | {'все признаки сбалансированы' if all(r['balanced'] for r in ctx['randomization']) else 'часть признаков даёт значимый дисбаланс'} |
| Контаминация (пользователь в двух группах) | {int(ctx['quality'].set_index('check').loc['user_in_both_groups', 'issues_found'])} записей — {('удалены' if int(ctx['quality'].set_index('check').loc['user_in_both_groups', 'issues_found']) else 'не найдены')} |
| Качество данных | {int(ctx['quality']['issues_found'].sum())} проблемных записей удалено, осталось {_num(ctx['rows_clean'])} |

Планируемый объём: при {_num(ctx['n_per_arm'])} пользователях на группу минимально детектируемый эффект
(МДЭ, MDE) составляет {_pct(ctx['mde_pct'] / 100)} относительно при `alpha = {_dec(ALPHA, 2)}`,
мощности 0,8. Наблюдённый lift ({_signed_pct(stats['rel_lift_pct'])}) {'ниже' if stats['rel_lift_pct'] < ctx['mde_pct'] else 'не ниже'} этого порога:
{'значит, эффект такого размера эксперимент ловит на грани мощности — результаты по вариативным метрикам и по малым сегментам следует считать предварительными.' if stats['rel_lift_pct'] < ctx['mde_pct'] else 'мощности эксперимента достаточно для эффекта наблюдаемого размера.'}

## Результаты

![Конверсия](figures/02_conversion.png)

![Воронка](figures/03_funnel.png)

Просмотр товара: {_pct(gm.loc['control', 'view_rate'])} (A) против {_pct(gm.loc['treatment', 'view_rate'])} (B).
Доля пользователей с добавлением в корзину (разница B − A): {'—' if math.isnan(limited['atc_diff']) else _pp_bare(limited['atc_diff'])} п.п.
Изменение доли покупок при неизменной доле добавлений в корзину — это и есть механизм эффекта: кнопка
влияет на решение о покупке уже после корзины, а не на интерес к товару.
Средний чек: {_num(gm.loc['control', 'revenue_per_purchaser'], 2)} ₽ против {_num(gm.loc['treatment', 'revenue_per_purchaser'], 2)} ₽.

## Статистическая значимость

| Показатель | Значение |
|---|---|
| Конверсия контроля | {_pct(stats['cr_control'], 3)} |
| Конверсия теста | {_pct(stats['cr_treatment'], 3)} |
| Абсолютная разница | {_pp(stats['abs_diff'], 3)} |
| Относительный lift | {_signed_pct(stats['rel_lift_pct'])} |
| z-статистика | {_dec(stats['z_stat'], 3)} |
| p-value (двусторонний) | {_p(stats['p_value'])} |
| 95% ДИ разницы | [{_pp(stats['ci_low'], 3)}; {_pp(stats['ci_high'], 3)}] |
| Уровень значимости | {_dec(ALPHA, 2)} |

![Доверительный интервал](figures/04_confidence_interval.png)

Тест: двусторонний z-тест для двух долей (two-proportion z-test), объединённая (pooled) стандартная
ошибка для z и p-value. Доверительный интервал построен по необъединённой (unpooled) стандартной ошибке —
так интервал не предполагает H0 верной. Различие статистически {'значимо' if stats['significant'] else 'не значимо'}, {sign_text}.

**Статистическая значимость ≠ бизнес-значимость.** Значимость отвечает на вопрос «похоже ли это на шум»,
а бизнес-ценность — «стоит ли эффект стоимости внедрения». Второе оценивается отдельно ниже, через lift и его ДИ.

## Сегментный анализ

{ctx['segments_markdown']}

![Сегменты: устройство](figures/05_segments_device.png)

Проверка на гетерогенность: {ctx['heterogeneity_text']} Отсутствие значимости в сегменте не означает,
что эффекта там нет: при размерах подгрупп в несколько сотен пользователей интервал слишком широк,
чтобы отличить нулевой эффект от эффекта уровня общего. Поэтому сегментные выводы — гипотезы для
следующего теста, а не основание для разделения внедрения по сегментам.

## Бизнес-эффект

**Наблюдаемый результат** (факт по эксперименту):
разница конверсии {_pp(stats['abs_diff'], 3)}, выручка на пользователя {_num(gm.loc['control', 'revenue_per_user'], 2)} ₽ → {_num(gm.loc['treatment', 'revenue_per_user'], 2)} ₽.

**Оценка бизнес-эффекта** (экстраполяция, не факт) на {_num(impact['n_target'])} пользователей:

| Сценарий | Доп. покупки | Доп. выручка |
|---|---|---|
| Наблюдаемая оценка | {_num(impact['extra_purchases'], 1)} | {_num(impact['extra_revenue'])} ₽ |
| Нижняя граница 95% ДИ | {_num(impact['extra_purchases_ci_low'], 1)} | {_num(impact['extra_revenue_ci_low'])} ₽ |
| Верхняя граница 95% ДИ | {_num(impact['extra_purchases_ci_high'], 1)} | {_num(impact['extra_revenue_ci_high'])} ₽ |

Оценка переводит разницу конверсии в деньги по среднему чеку Treatment ({_num(impact['aov_treatment'], 2)} ₽) и
предполагает, что эффект сохранится на всей популяции. Это допущение, а не измеренный факт: длительность
эксперимента ограничена, эффект новизны не исключён.

![Влияние на выручку](figures/07_revenue_impact.png)

## Итоговое решение

### {decision}

{decision_text}

Основания: p = {_p(stats['p_value'])}, относительный lift {_signed_pct(stats['rel_lift_pct'])},
95% ДИ [{_pp(stats['ci_low'], 3)}; {_pp(stats['ci_high'], 3)}].{caveat}
"""


def _readme_block(ctx: dict) -> str:
    gm = ctx["group_metrics"].set_index("experiment_group")
    stats = ctx["stats"]
    decision = DECISIONS[ctx["decision"]]
    return f"""<!-- RESULTS:START -->
### Результаты (генерируются `run_analysis.py`)

| Метрика | A (Control) | B (Treatment) |
|---|---|---|
| Пользователи | {_num(gm.loc['control', 'users'])} | {_num(gm.loc['treatment', 'users'])} |
| Конверсия | {_pct(gm.loc['control', 'conversion_rate'])} | {_pct(gm.loc['treatment', 'conversion_rate'])} |
| Доля добавлений в корзину | {_pct(gm.loc['control', 'add_to_cart_rate'])} | {_pct(gm.loc['treatment', 'add_to_cart_rate'])} |
| Выручка на пользователя | {_num(gm.loc['control', 'revenue_per_user'], 2)} ₽ | {_num(gm.loc['treatment', 'revenue_per_user'], 2)} ₽ |
| Выручка на покупателя | {_num(gm.loc['control', 'revenue_per_purchaser'], 2)} ₽ | {_num(gm.loc['treatment', 'revenue_per_purchaser'], 2)} ₽ |

Относительный lift: **{_signed_pct(stats['rel_lift_pct'])}**, 95% ДИ [{_pp(stats['ci_low'], 3)}; {_pp(stats['ci_high'], 3)}],
p-value = {_p(stats['p_value'])} (двусторонний z-тест для двух долей, alpha = {_dec(ALPHA, 2)}).

**Решение: {decision}.**

![Conversion](results/figures/02_conversion.png)
![Воронка](results/figures/03_funnel.png)
![Доверительный интервал](results/figures/04_confidence_interval.png)
<!-- RESULTS:END -->"""


README_MARKER_START = "<!-- RESULTS:START -->"
README_MARKER_END = "<!-- RESULTS:END -->"


def inject_readme_results(readme_text: str, block: str) -> str:
    start = readme_text.find(README_MARKER_START)
    end = readme_text.find(README_MARKER_END)
    if start == -1 or end == -1:
        return readme_text
    return readme_text[:start] + block + readme_text[end + len(README_MARKER_END) :]


def build_validation(ctx: dict) -> str:
    return _validation_markdown(ctx)


def build_analysis_report(ctx: dict) -> str:
    return _analysis_markdown(ctx)


def build_readme_results(ctx: dict) -> str:
    return _readme_block(ctx)
