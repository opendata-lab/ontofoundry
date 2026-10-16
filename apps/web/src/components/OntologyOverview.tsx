import { Button, Card, Statistic, Tooltip, Typography } from "antd";
import { ArrowUpRight, LockKeyhole, Maximize, Minus, Plus } from "lucide-react";
import { useId, useState, type CSSProperties, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { WorkspaceOverview } from "../api/types";
import { useElementInspector } from "../hooks/useElementInspector";
import type { SelectedGraphItem } from "./OntologyGraph";

const { Text } = Typography;

type Layer = "service" | "semantic" | "instance" | "mapping";
const layers: { id: Layer; title: string; y: number; width: number; height: number; color: string; fill: string }[] = [
  { id: "service", title: "服务层", y: 95, width: 470, height: 80, color: "--color-rule-label", fill: "--color-rule-label-soft" },
  { id: "semantic", title: "语义模型层", y: 235, width: 530, height: 108, color: "--color-object", fill: "--color-object-soft" },
  { id: "instance", title: "实例与证据层", y: 385, width: 580, height: 130, color: "--color-attribute", fill: "--color-attribute-soft" },
  { id: "mapping", title: "数据映射层", y: 540, width: 630, height: 150, color: "--color-relation", fill: "--color-relation-soft" },
];
const layerStyle = (layer: (typeof layers)[number]) =>
  ({ "--layer-color": `var(${layer.color})`, "--layer-fill": `var(${layer.fill})` }) as CSSProperties;

function point(layer: (typeof layers)[number], u: number, v: number) {
  return { x: 470 + ((u - v) * layer.width) / 2, y: layer.y + ((u + v - 1) * layer.height) / 2 };
}
function positions(items: { id: string }[], layer: (typeof layers)[number]) {
  const columns = Math.min(6, Math.max(1, Math.ceil(Math.sqrt(items.length))));
  const rows = Math.ceil(items.length / columns);
  return new Map(
    items.map((item, i) => [
      item.id,
      point(
        layer,
        columns === 1 ? 0.5 : 0.18 + ((i % columns) / (columns - 1)) * 0.64,
        rows === 1 ? 0.5 : 0.18 + (Math.floor(i / columns) / (rows - 1)) * 0.64,
      ),
    ]),
  );
}

const NODE =
  "cursor-pointer fill-[var(--layer-color)] outline-none active:opacity-60 [&:focus-visible_.hit]:stroke-focus [&:focus-visible_.hit]:[stroke-width:2] [&:hover_.hit]:fill-[var(--layer-fill)] [&:hover_.hit]:stroke-[var(--layer-color)]";
const LABEL = "fill-ink-2 font-sans text-[12px]";
const EMPTY = "fill-muted font-sans text-[12px] [text-anchor:middle]";

function DataNode({
  x,
  y,
  label,
  name,
  showText,
  square,
  onOpen,
}: {
  x: number;
  y: number;
  label: string;
  name: string;
  showText: boolean;
  square?: boolean;
  onOpen: () => void;
}) {
  return (
    <g
      className={NODE}
      transform={`translate(${x} ${y})`}
      role="button"
      tabIndex={0}
      aria-label={label}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
    >
      <title>{name}</title>
      <circle className="hit fill-transparent stroke-transparent" r="18" />
      {square ? <rect x="-5" y="-5" width="10" height="10" rx="2" /> : <circle r="5" />}
      {showText && (
        <text x="11" y="4" className={LABEL}>
          {name.length > 12 ? name.slice(0, 12) + "…" : name}
        </text>
      )}
    </g>
  );
}

export function OntologyOverview({
  overview,
  onSemantic,
  onSelect,
}: {
  overview: WorkspaceOverview;
  onSemantic: () => void;
  onSelect: (value: SelectedGraphItem) => void;
}) {
  const [active, setActive] = useState<Layer | null>(null);
  const [zoom, setZoom] = useState(1);
  const pattern = useId().replace(/:/g, "");
  const inspector = useElementInspector();
  const { details } = overview;
  const graph = overview.graph ?? { nodes: [], edges: [] };
  const counts = overview.version?.counts;
  const types = graph.nodes;
  const shownTypes = types.slice(0, 24);
  const objects = details?.objects ?? [];
  const mappings = details?.mappings ?? [];
  const typePositions = positions(shownTypes, layers[1]);
  const objectPositions = positions(objects, layers[2]);
  const mappingPositions = positions(mappings, layers[3]);
  const relations = graph.edges.filter((e) => e.kind === "link_type");
  const typeName = (id: string) => types.find((t) => t.id === id)?.label ?? "对象";
  const line = (id: string, from?: { x: number; y: number }, to?: { x: number; y: number }) =>
    from && to ? (
      <line
        key={id}
        className="stroke-[var(--layer-color)] [stroke-opacity:0.45] [stroke-width:1]"
        x1={from.x}
        y1={from.y}
        x2={to.x}
        y2={to.y}
      />
    ) : null;
  const stats: Record<Layer, { title: string; value: number | string }[]> = {
    service: [
      { title: "REST API", value: "可用" },
      { title: "MCP", value: "可用" },
    ],
    semantic: [
      { title: "对象", value: counts?.object_types ?? types.length },
      { title: "关系", value: counts?.link_types ?? relations.length },
      { title: "指标", value: counts?.metrics ?? 0 },
    ],
    instance: details
      ? [
          { title: "文档实例", value: details.object_count ?? 0 },
          { title: "实例关系", value: details.link_count ?? 0 },
          { title: "来源材料", value: details.evidence_material_count ?? 0 },
        ]
      : [],
    mapping: details
      ? [
          { title: "对象映射", value: details.mapping_count ?? 0 },
          { title: "数据集", value: counts?.datasets ?? 0 },
        ]
      : [],
  };
  const action: Record<Layer, ReactNode> = {
    service: <Link to="../delivery">本体发布</Link>,
    semantic: (
      <Button type="link" size="small" className="!h-auto !p-0" onClick={onSemantic}>
        进入语义视图
      </Button>
    ),
    instance: <Link to="../objects">浏览本体对象</Link>,
    mapping: details ? <Link to="../mappings">管理映射</Link> : null,
  };
  return (
    <section
      className="grid h-full min-h-0 grid-cols-[220px_minmax(0,1fr)] gap-4 bg-surface px-6 py-5 text-ink"
      aria-label="已发布本体分层总览"
    >
      <div className="flex min-h-0 flex-col justify-center gap-3" aria-label="本体层级">
        {layers.map((layer) => {
          const restricted = !details && (layer.id === "instance" || layer.id === "mapping");
          return (
            <Card
              key={layer.id}
              size="small"
              style={layerStyle(layer)}
              className={`cursor-pointer border-l-4! border-l-[var(--layer-color)]! ${active === layer.id ? "bg-[var(--layer-fill)]!" : ""}`}
              onClick={() => setActive((current) => (current === layer.id ? null : layer.id))}
              aria-pressed={active === layer.id}
              role="button"
            >
              <div className="flex items-center justify-between">
                <Text strong className="text-[var(--layer-color)]!">
                  {layer.title}
                </Text>
                {!restricted && action[layer.id] && (
                  <span className="inline-flex items-center gap-0.5 text-xs" onClick={(e) => e.stopPropagation()}>
                    {action[layer.id]}
                    <ArrowUpRight size={12} />
                  </span>
                )}
              </div>
              {restricted ? (
                <Text type="secondary" className="mt-1 inline-flex items-center gap-1 text-xs">
                  <LockKeyhole size={12} />
                  仅空间成员可见
                </Text>
              ) : (
                <div className="mt-1 flex flex-wrap gap-x-4">
                  {stats[layer.id].map((s) => (
                    <Statistic
                      key={s.title}
                      title={<span className="text-xs">{s.title}</span>}
                      value={s.value}
                      valueStyle={{ fontSize: 16 }}
                    />
                  ))}
                </div>
              )}
            </Card>
          );
        })}
      </div>
      <div className="relative min-h-0 min-w-0 overflow-clip">
        <svg className="block size-full" viewBox="0 0 880 640" role="group" aria-label="服务、语义模型、实例与证据、数据映射四层图">
          <defs>
            <pattern id={pattern} width="12" height="12" patternUnits="userSpaceOnUse">
              <path d="M12 0H0V12" className="fill-none stroke-rule-strong [stroke-width:0.4]" />
            </pattern>
          </defs>
          <g transform={`translate(${440 * (1 - zoom)} ${320 * (1 - zoom)}) scale(${zoom})`}>
            {layers.map((layer) => {
              const points = [
                [0, 0],
                [1, 0],
                [1, 1],
                [0, 1],
              ]
                .map(([u, v]) => point(layer, u, v))
                .map((p) => p.x + "," + p.y)
                .join(" ");
              const muted = active && active !== layer.id;
              return (
                <g
                  key={layer.id}
                  data-layer={layer.id}
                  style={layerStyle(layer)}
                  className={`transition-opacity duration-100 ${muted ? "[&_.plane]:opacity-30" : ""}`}
                >
                  <polygon
                    points={points}
                    className="plane fill-[var(--layer-fill)] stroke-[var(--layer-color)] [fill-opacity:0.6] [stroke-opacity:0.55] [stroke-width:1]"
                  />
                  <polygon points={points} fill={`url(#${pattern})`} className="plane opacity-[0.22]" />
                  {layer.id === "service" &&
                    ["REST API", "MCP"].map((name, i) => (
                      <g key={name} className="fill-[var(--layer-color)]" transform={`translate(${410 + i * 118} 95)`}>
                        <circle r="5" />
                        <text x="12" y="4" className={LABEL}>
                          {name}
                        </text>
                      </g>
                    ))}
                  {layer.id === "semantic" && (
                    <>
                      <g aria-hidden="true" className="plane">
                        {relations.map((r) => line(r.id, typePositions.get(r.source), typePositions.get(r.target)))}
                      </g>
                      {shownTypes.map((type) => {
                        const p = typePositions.get(type.id)!;
                        return (
                          <DataNode
                            key={type.id}
                            {...p}
                            label={"查看本体：" + type.label}
                            name={type.label}
                            showText={shownTypes.length <= 8}
                            onOpen={() => onSelect({ category: "node", item: type })}
                          />
                        );
                      })}
                      {types.length > shownTypes.length && (
                        <text className={EMPTY} x="470" y={layer.y + 68}>
                          概览展示 {shownTypes.length} / {types.length} 个对象，进入语义视图查看全部
                        </text>
                      )}
                    </>
                  )}
                  {layer.id === "instance" && (
                    <>
                      <g aria-hidden="true" className="plane">
                        {(details?.links ?? []).map((r) =>
                          line(r.id, objectPositions.get(r.source_id), objectPositions.get(r.target_id)),
                        )}
                      </g>
                      {objects.map((o) => (
                        <DataNode
                          key={o.id}
                          {...objectPositions.get(o.id)!}
                          label={"查看实例：" + o.display_text}
                          name={o.display_text}
                          showText={objects.length <= 8}
                          onOpen={() => inspector.open({ kind: "material_object", id: o.id, sessionId: null })}
                        />
                      ))}
                      {!objects.length && (
                        <text className={EMPTY} x="470" y={layer.y + 4}>
                          {details ? "暂无已发布文档实例" : "仅空间成员可见"}
                        </text>
                      )}
                      {details && (details.object_count ?? 0) > objects.length && (
                        <text className={EMPTY} x="470" y={layer.y + 78}>
                          概览展示 {objects.length} / {details.object_count} 个实例
                        </text>
                      )}
                    </>
                  )}
                  {layer.id === "mapping" && (
                    <>
                      {mappings.map((m) => (
                        <DataNode
                          key={m.id}
                          {...mappingPositions.get(m.id)!}
                          square
                          label={"查看映射：" + typeName(m.type_id)}
                          name={typeName(m.type_id)}
                          showText={mappings.length <= 8}
                          onOpen={() => inspector.open({ kind: "mapping", id: m.id, sessionId: null })}
                        />
                      ))}
                      {!mappings.length && (
                        <text className={EMPTY} x="470" y={layer.y + 4}>
                          {details ? "暂无已发布数据映射" : "仅空间成员可见"}
                        </text>
                      )}
                      {details && (details.mapping_count ?? 0) > mappings.length && (
                        <text className={EMPTY} x="470" y={layer.y + 88}>
                          概览展示 {mappings.length} / {details.mapping_count} 条映射
                        </text>
                      )}
                    </>
                  )}
                </g>
              );
            })}
          </g>
        </svg>
        <div
          className="absolute right-2 bottom-3 flex items-center gap-1 rounded-xs border border-rule bg-surface p-1"
          aria-label="全局图缩放"
        >
          <Tooltip title="放大">
            <Button
              size="small"
              type="text"
              aria-label="放大全局图"
              disabled={zoom >= 1.6}
              icon={<Plus size={15} />}
              onClick={() => setZoom((v) => Math.min(1.6, +(v + 0.2).toFixed(1)))}
            />
          </Tooltip>
          <span className="min-w-[34px] text-center text-[11px] tabular-nums">{Math.round(zoom * 100)}%</span>
          <Tooltip title="缩小">
            <Button
              size="small"
              type="text"
              aria-label="缩小全局图"
              disabled={zoom <= 0.6}
              icon={<Minus size={15} />}
              onClick={() => setZoom((v) => Math.max(0.6, +(v - 0.2).toFixed(1)))}
            />
          </Tooltip>
          <Tooltip title="适配">
            <Button
              size="small"
              type="text"
              aria-label="适配全局图"
              icon={<Maximize size={14} />}
              onClick={() => {
                setZoom(1);
                setActive(null);
              }}
            />
          </Tooltip>
        </div>
      </div>
    </section>
  );
}
