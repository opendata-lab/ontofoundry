import { Button, Tooltip } from "antd";
import { Maximize, Minus, Plus } from "lucide-react";
import { useId, useState } from "react";
import type { ObjectType } from "../../api/types";
import { byId, effectiveLinks } from "../../lib/coreModel";
import type { PanelProps } from "../../lib/elementModel";
import { SectionTitle } from "../layout";
import { shortObjectName } from "../../lib/objectMapping";

type Group = { names: string[]; incoming: boolean; outgoing: boolean };

/** All neighbours share one radial canvas; parallel relations share one counted edge. */
export function ObjectRelationGraph({ draft, type, open }: PanelProps<ObjectType>) {
  const [zoom, setZoom] = useState(1);
  const marker = useId().replaceAll(":", "");
  const links = effectiveLinks(draft, type.id);
  const groups = new Map<string, Group>();
  for (const { definition, direction } of links) {
    const self = definition.source_type_id === definition.target_type_id;
    const other = self
      ? type.id
      : direction === "forward"
        ? definition.target_type_id
        : definition.source_type_id;
    if (!byId(draft.object_types, other)) continue;
    const group = groups.get(other) ?? { names: [], incoming: false, outgoing: false };
    group.names.push(shortObjectName(definition));
    if (self || direction === "forward") group.outgoing = true;
    if (self || direction === "reverse") group.incoming = true;
    groups.set(other, group);
  }
  const neighbours = [...groups].filter(([id]) => id !== type.id);
  const rx = Math.max(240, neighbours.length * 14);
  const ry = Math.max(190, neighbours.length * 11);
  const width = rx * 2 + 160;
  const height = ry * 2 + 140;
  const cx = width / 2;
  const cy = height / 2;
  const crowded = neighbours.length > 8;
  const connection = (id: string, group: Group, path: string, x: number, y: number) => (
    <g key={`edge:${id}`} role="group" tabIndex={0} aria-label={group.names.join("、")} className="group outline-none">
      <title>{group.names.join("\n")}</title>
      <path d={path} className="fill-none stroke-transparent" strokeWidth={14} />
      <path
        d={path}
        className="fill-none stroke-rule-strong group-hover:stroke-accent group-focus:stroke-accent"
        strokeWidth={1.5}
        markerStart={group.incoming ? `url(#${marker}-start)` : undefined}
        markerEnd={group.outgoing ? `url(#${marker}-end)` : undefined}
      />
      {(!crowded || group.names.length > 1) && (
        <text x={x} y={y - 16} textAnchor="middle" className="fill-muted text-xs">
          {group.names.length === 1 ? group.names[0] : `${group.names.length} 条关系`}
        </text>
      )}
    </g>
  );
  return (
    <section className="flex min-w-0 flex-col gap-2">
      <SectionTitle title="关系" className="min-h-7">
        {links.length > 0 && (
          <Button type="link" size="small" onClick={() => open({ kind: "object_type", id: type.id, tab: "relations" })}>
            全部关系
          </Button>
        )}
      </SectionTitle>
      <div className="relative overflow-hidden rounded-md border border-rule bg-surface-raised">
        <svg className="object-overview-graph" viewBox={`0 0 ${width} ${height}`} aria-label={`${shortObjectName(type)}的关系图`}>
          <defs>
            {(["end", "start"] as const).map((side) => (
              <marker
                key={side}
                id={`${marker}-${side}`}
                viewBox="0 0 10 10"
                refX={side === "end" ? 9 : 1}
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto"
              >
                <path d={side === "end" ? "M0 0 10 5 0 10" : "M10 0 0 5 10 10"} className="fill-rule-strong" />
              </marker>
            ))}
          </defs>
          <g transform={`translate(${cx} ${cy}) scale(${zoom}) translate(${-cx} ${-cy})`}>
            {neighbours.map(([id, group], i) => {
              const angle = -Math.PI / 2 + (i * Math.PI * 2) / neighbours.length;
              const dx = Math.cos(angle) * rx;
              const dy = Math.sin(angle) * ry;
              const x = cx + dx;
              const y = cy + dy;
              const t0 = Math.min(60 / Math.max(Math.abs(dx), 0.01), 26 / Math.max(Math.abs(dy), 0.01));
              const t1 = Math.min(51 / Math.max(Math.abs(dx), 0.01), 18 / Math.max(Math.abs(dy), 0.01));
              const name = shortObjectName(byId(draft.object_types, id)!);
              return (
                <g key={id}>
                  {connection(
                    id,
                    group,
                    `M${cx + dx * t0},${cy + dy * t0} L${x - dx * t1},${y - dy * t1}`,
                    cx + dx * 0.62,
                    cy + dy * 0.62,
                  )}
                  <g
                    role="button"
                    tabIndex={0}
                    aria-label={`打开${name}`}
                    className="cursor-pointer outline-none [&:hover_rect]:stroke-accent [&:focus_rect]:stroke-accent"
                    onClick={() => open({ kind: "object_type", id })}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        open({ kind: "object_type", id });
                      }
                    }}
                  >
                    <title>{name}</title>
                    <rect x={x - 50} y={y - 17} width={100} height={34} rx={6} className="fill-surface stroke-rule-strong" />
                    <text x={x} y={y + 4} textAnchor="middle" className="fill-ink text-sm">
                      {name.length > 7 ? name.slice(0, 7) + "…" : name}
                    </text>
                  </g>
                </g>
              );
            })}
            {groups.has(type.id) && (() => {
              // Put the loop between radial edges, away from their labels.
              const angle = neighbours.length === 0 ? -Math.PI / 2 : -Math.PI / 2 + Math.PI / neighbours.length;
              const point = (direction: number, radius: number) => ({ x: cx + Math.cos(direction) * radius, y: cy + Math.sin(direction) * radius });
              const boundary = (direction: number) => point(direction, Math.min(59 / Math.max(Math.abs(Math.cos(direction)), 0.01), 25 / Math.max(Math.abs(Math.sin(direction)), 0.01)));
              const start = boundary(angle - 0.4);
              const end = boundary(angle + 0.4);
              const first = point(angle - 0.6, 150);
              const second = point(angle + 0.6, 150);
              const label = point(angle, 120);
              return connection(type.id, groups.get(type.id)!, `M${start.x},${start.y} C${first.x},${first.y} ${second.x},${second.y} ${end.x},${end.y}`, label.x, label.y);
            })()}
            <g>
              <rect x={cx - 59} y={cy - 25} width={118} height={50} rx={7} className="fill-object-soft stroke-object" />
              <text x={cx} y={cy + 4} textAnchor="middle" className="fill-object text-sm font-semibold">
                {shortObjectName(type)}
              </text>
            </g>
          </g>
        </svg>
        <div className="absolute right-2 bottom-2 flex flex-col gap-1">
          <Tooltip title="放大" placement="left">
            <Button size="small" aria-label="放大关系图" icon={<Plus size={14} />} onClick={() => setZoom(Math.min(2.4, zoom + 0.1))} />
          </Tooltip>
          <Tooltip title="缩小" placement="left">
            <Button size="small" aria-label="缩小关系图" icon={<Minus size={14} />} onClick={() => setZoom(Math.max(0.2, zoom - 0.1))} />
          </Tooltip>
          <Tooltip title="适应画布" placement="left">
            <Button size="small" aria-label="适应关系画布" icon={<Maximize size={14} />} onClick={() => setZoom(1)} />
          </Tooltip>
        </div>
      </div>
    </section>
  );
}
