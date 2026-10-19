import { useTranslations } from "next-intl";

import { plateList, plateLook } from "@/features/training/plates";
import type { PlatesOut } from "@/features/training/types";
import { useTrainingFormat } from "@/features/training/use-training-format";

const HEIGHT = 120;
const SLEEVE = 34;
const GAP = 1.5;

/**
 * A barbell seen from the front, drawn from the API's `/v1/training/plates` answer: the same
 * plates on each side, heaviest next to the collar, coloured by weight.
 */
export function PlateBar({ answer }: { answer: PlatesOut }) {
  const t = useTranslations("workout.plates");
  const fmt = useTrainingFormat();
  const side = answer.per_side;
  const list = plateList(side, (kg) => fmt.number(kg, 2));
  const bar = fmt.kg(answer.bar_kg);
  const sideWidth = side.reduce((sum, kg) => sum + plateLook(kg).width + GAP, 0);
  const sleeve = Math.max(SLEEVE, sideWidth + 8);
  const shaft = 70;
  const width = 2 * (sleeve + 6) + shaft;
  const mid = HEIGHT / 2;

  // Left side: collar at the shaft, plates going outwards (heaviest innermost).
  const left: { kg: number; x: number }[] = [];
  let x = sleeve + 3;
  for (const kg of side) {
    const w = plateLook(kg).width;
    x -= w + GAP;
    left.push({ kg, x });
  }
  const right: { kg: number; x: number }[] = [];
  x = sleeve + 9 + shaft;
  for (const kg of side) {
    right.push({ kg, x: x + GAP });
    x += plateLook(kg).width + GAP;
  }

  return (
    <figure data-testid="plate-bar" data-per-side={side.join(",")} className="space-y-3">
      <svg
        viewBox={`0 0 ${width} ${HEIGHT}`}
        className="h-32 w-full"
        role="img"
        aria-label={side.length ? t("barLabel", { bar, plates: list }) : t("emptyBarLabel", { bar })}
      >
        {/* sleeves and shaft */}
        <rect x={2} y={mid - 4} width={sleeve + 4} height={8} rx={2} fill="var(--bar-sleeve)" />
        <rect x={width - sleeve - 6} y={mid - 4} width={sleeve + 4} height={8} rx={2} fill="var(--bar-sleeve)" />
        <rect x={sleeve + 6} y={mid - 2.5} width={shaft} height={5} fill="var(--bar-shaft)" />
        <rect x={sleeve + 3} y={mid - 9} width={3} height={18} fill="var(--bar-shaft)" />
        <rect x={sleeve + 6 + shaft} y={mid - 9} width={3} height={18} fill="var(--bar-shaft)" />
        {[...left.map((p) => ({ ...p, side: "left" })), ...right.map((p) => ({ ...p, side: "right" }))].map((p, i) => {
          const look = plateLook(p.kg);
          const h = (HEIGHT - 8) * look.height;
          return (
            <rect
              key={`${p.side}-${i}`}
              data-plate={p.kg}
              data-side={p.side}
              data-color={look.name}
              x={p.x}
              y={mid - h / 2}
              width={look.width}
              height={h}
              rx={1.5}
              fill={look.color}
              stroke={look.stroke}
              strokeWidth={1}
            />
          );
        })}
      </svg>
      <figcaption className="space-y-1 text-sm">
        <p className="text-label font-semibold uppercase tracking-[0.08em] text-muted">{t("eachSide")}</p>
        <p className="text-3xl font-black tabular tracking-tight" data-testid="plates-per-side">
          {side.length ? list : t("empty")}
        </p>
        <p className="text-muted">
          {t("loaded", { bar, loaded: fmt.kg(answer.achieved_kg) })}
          {answer.exact
            ? null
            : ` · ${t(answer.difference_kg >= 0 ? "under" : "over", { difference: fmt.kg(Math.abs(answer.difference_kg)), target: fmt.kg(answer.target_kg) })}`}
        </p>
        <ul className="flex flex-wrap gap-1.5 pt-1" aria-label={t("sideList")}>
          {side.map((kg, i) => {
            const look = plateLook(kg);
            return (
              <li key={i} className="inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs font-medium">
                <span aria-hidden="true" className="size-2.5 rounded-full" style={{ background: look.color, outline: `1px solid ${look.stroke}` }} />
                {t("chip", { weight: fmt.kg(kg), color: t(`colors.${look.name}`) })}
              </li>
            );
          })}
        </ul>
      </figcaption>
    </figure>
  );
}
