import { Maximize, Minus, Plus } from "lucide-react";
import { useId, useState } from "react";
import {
  isObject,
  relationObjects,
  relationSource,
  type PanelProps,
} from "../../lib/elementModel";
import { objectMapping, shortObjectName } from "../../lib/objectMapping";

/** All neighbours share one radial canvas; parallel relations share one counted edge. */
export function ObjectRelationGraph(props: PanelProps) {
  const [zoom, setZoom] = useState(1);
  const marker = useId().replaceAll(":", "");
  const { draft, type, nativeDraft, open } = props;
  if (!isObject(type)) return null;
  const groups = new Map<
    string,
    { names: string[]; incoming: boolean; outgoing: boolean }
  >();
  const relations = objectMapping(draft, type, nativeDraft).relations;
  for (const row of relations) {
    const source = relationSource(row.definition);
    const subject = row.inheritedFrom ?? type.id;
    const ids = relationObjects(row.definition).filter((id) => id !== subject);
    // A self relation has only one distinct endpoint.
    if (
      source === subject &&
      (row.definition.roles?.some(
        (r) => r.concept.kind === "object_type" && r.concept.ref === subject,
      ) ||
        row.definition.target_type_id === subject)
    )
      ids.push(subject);
    for (const original of ids) {
      const id = original === subject ? type.id : original;
      if (!draft.object_types.some((o) => o.id === id)) continue;
      const group = groups.get(id) ?? {
        names: [],
        incoming: false,
        outgoing: false,
      };
      group.names.push(shortObjectName(row.definition));
      group.incoming ||= row.incoming;
      group.outgoing ||= !row.incoming;
      groups.set(id, group);
    }
  }
  const neighbours = [...groups].filter(([id]) => id !== type.id);
  const rx = Math.max(240, neighbours.length * 14),
    ry = Math.max(190, neighbours.length * 11);
  const width = rx * 2 + 160,
    height = ry * 2 + 140,
    cx = width / 2,
    cy = height / 2;
  const connection = (
    id: string,
    group: typeof groups extends Map<string, infer G> ? G : never,
    path: string,
    x: number,
    y: number,
  ) => (
    <g
      className={`om-graph-connection${neighbours.length > 8 ? " is-crowded" : ""}`}
      key={`edge:${id}`}
      tabIndex={0}
      aria-label={[...group.names].join("、")}
    >
      <title>{[...group.names].join("\n")}</title>
      <path className="om-edge-hit" d={path} />
      <path
        className="om-edge"
        d={path}
        markerStart={group.incoming ? `url(#${marker}-start)` : undefined}
        markerEnd={group.outgoing ? `url(#${marker}-end)` : undefined}
      />
      {group.names.length === 1 && (
        <text className="om-edge-label" x={x} y={y - 16} textAnchor="middle">
          {[...group.names][0]}
        </text>
      )}
      <g className="om-edge-count">
        <circle cx={x} cy={y} r={11} />
        <text x={x} y={y + 4} textAnchor="middle">
          {group.names.length}
        </text>
      </g>
    </g>
  );
  return (
    <section className="om-summary om-graph-pane">
      <div className="om-section-head">
        <h3>关系</h3>
        {relations.length > 0 && (
          <button
            type="button"
            className="element-text-button om-push"
            onClick={() =>
              open({ kind: "object_type", id: type.id, tab: "relations" })
            }
          >
            全部关系 ↗
          </button>
        )}
      </div>
      <div className="om-mini-graph">
        <svg
          className="om-graph-canvas"
          viewBox={`0 0 ${width} ${height}`}
          aria-label={`${shortObjectName(type)}的关系图`}
        >
          <defs>
            <marker
              id={`${marker}-end`}
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto"
            >
              <path d="M0 0 10 5 0 10" fill="var(--color-graph-edge)" />
            </marker>
            <marker
              id={`${marker}-start`}
              viewBox="0 0 10 10"
              refX="1"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto"
            >
              <path d="M10 0 0 5 10 10" fill="var(--color-graph-edge)" />
            </marker>
          </defs>
          <g
            transform={`translate(${cx} ${cy}) scale(${zoom}) translate(${-cx} ${-cy})`}
          >
            {neighbours.map(([id, group], i) => {
              const angle =
                  -Math.PI / 2 + (i * Math.PI * 2) / neighbours.length,
                dx = Math.cos(angle) * rx,
                dy = Math.sin(angle) * ry,
                x = cx + dx,
                y = cy + dy;
              const t0 = Math.min(
                  60 / Math.max(Math.abs(dx), 0.01),
                  26 / Math.max(Math.abs(dy), 0.01),
                ),
                t1 = Math.min(
                  51 / Math.max(Math.abs(dx), 0.01),
                  18 / Math.max(Math.abs(dy), 0.01),
                );
              const object = draft.object_types.find((o) => o.id === id)!;
              const name = shortObjectName(object);
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
                    className="om-graph-node"
                    role="button"
                    tabIndex={0}
                    aria-label={`打开${name}`}
                    onClick={() => open({ kind: "object_type", id })}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        open({ kind: "object_type", id });
                      }
                    }}
                  >
                    <title>{name}</title>
                    <rect
                      x={x - 50}
                      y={y - 17}
                      width={100}
                      height={34}
                      rx={6}
                    />
                    <text x={x} y={y + 4} textAnchor="middle">
                      {name.length > 7 ? name.slice(0, 7) + "…" : name}
                    </text>
                  </g>
                </g>
              );
            })}
            {groups.has(type.id) &&
              connection(
                type.id,
                groups.get(type.id)!,
                `M${cx - 35},${cy - 25} C${cx - 110},${cy - 105} ${cx + 110},${cy - 105} ${cx + 35},${cy - 25}`,
                cx,
                cy - 85,
              )}
            <g className="om-graph-node is-current">
              <rect x={cx - 59} y={cy - 25} width={118} height={50} rx={7} />
              <text x={cx} y={cy + 4} textAnchor="middle">
                {shortObjectName(type)}
              </text>
            </g>
          </g>
        </svg>
        <div className="om-graph-controls">
          <button
            type="button"
            className="icon-button"
            aria-label="放大关系图"
            onClick={() => setZoom(Math.min(2.4, zoom + 0.1))}
          >
            <Plus size={16} />
          </button>
          <button
            type="button"
            className="icon-button"
            aria-label="缩小关系图"
            onClick={() => setZoom(Math.max(0.2, zoom - 0.1))}
          >
            <Minus size={16} />
          </button>
          <button
            type="button"
            className="icon-button"
            aria-label="适应关系画布"
            onClick={() => setZoom(1)}
          >
            <Maximize size={16} />
          </button>
        </div>
      </div>
    </section>
  );
}
