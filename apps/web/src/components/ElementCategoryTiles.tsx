import { Button } from "antd";
import { Layers, type LucideIcon } from "lucide-react";
import type { TargetKind } from "../api/types";
import { ELEMENT_CATEGORIES, type ElementCategory } from "../lib/elementCategories";


function Tile({ icon: Icon, text, total, selected, tone, background, onClick }: {
  icon: LucideIcon; text: string; total: number; selected: boolean; tone: string; background: string; onClick: () => void;
}) {
  return (
    <Button aria-pressed={selected} aria-label={`${text} ${total}`}
      className={`h-auto min-w-0 justify-start gap-2 rounded-md px-2 py-2 text-xs ${selected ? "border-accent text-accent" : tone}`}
      onClick={onClick}>
      <span className={`inline-flex size-5 flex-none items-center justify-center rounded-xs ${background} ${tone}`}><Icon size={14} /></span>
      <span className="min-w-0 truncate">{text}</span>
      <span className="ml-auto flex-none font-semibold tabular-nums">{total}</span>
    </Button>
  );
}

/**
 * Category tiles with counts, shared by the draft and the proposal review.
 * With `allTotal`, a leading 全部 tile selects no category (null).
 */
export function ElementCategoryTiles({ label, categories = ELEMENT_CATEGORIES, count, selected, onSelect, allTotal }: {
  label: string;
  categories?: ElementCategory[];
  count: (kind: TargetKind) => number;
  selected: TargetKind | null;
  onSelect: (kind: TargetKind | null) => void;
  allTotal?: number;
}) {
  return (
    <div className="model-result-categories" aria-label={label}>
      {allTotal !== undefined && (
        <Tile icon={Layers} text="全部" total={allTotal} selected={selected === null} tone="text-ink-2" background="bg-canvas" onClick={() => onSelect(null)} />
      )}
      {categories.map((category) => (
        <Tile key={category.key} icon={category.icon} text={category.text} tone={category.tone} background={category.background}
          total={count(category.key)} selected={selected === category.key} onClick={() => onSelect(category.key)} />
      ))}
    </div>
  );
}
