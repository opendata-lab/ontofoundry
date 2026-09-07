import { useId, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowUpRight, LockKeyhole, Maximize, Minus, Plus } from "lucide-react";
import type { WorkspaceOverview } from "../api/types";
import type { SelectedGraphItem } from "./OntologyGraph";
import "../styles/ontology-overview.css";

type Layer = "service" | "semantic" | "instance" | "mapping";
const layers: {
  id: Layer;
  title: string;
  y: number;
  width: number;
  height: number;
}[] = [
  { id: "service", title: "服务层", y: 95, width: 470, height: 80 },
  { id: "semantic", title: "语义模型层", y: 235, width: 530, height: 108 },
  { id: "instance", title: "实例与证据层", y: 385, width: 580, height: 130 },
  { id: "mapping", title: "数据映射层", y: 540, width: 630, height: 150 },
];

function point(layer: (typeof layers)[number], u: number, v: number) {
  return {
    x: 470 + ((u - v) * layer.width) / 2,
    y: layer.y + ((u + v - 1) * layer.height) / 2,
  };
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
  const navigate = useNavigate();
  const { graph, details } = overview;
  const types = graph.nodes.filter((n) => n.kind === "object_type");
  const shownTypes = types.slice(0, 24);
  const objects = details?.objects ?? [];
  const mappings = details?.mappings ?? [];
  const typePositions = positions(shownTypes, layers[1]);
  const objectPositions = positions(objects, layers[2]);
  const mappingPositions = positions(mappings, layers[3]);
  const relations = graph.edges.filter((e) => e.kind === "link_type");
  const toggle = (id: Layer) =>
    setActive((current) => (current === id ? null : id));
  const visitObject = (typeId: string, id: string) =>
    navigate("../objects/" + typeId + "/instances/" + id);
  const line = (
    id: string,
    from: { x: number; y: number } | undefined,
    to: { x: number; y: number } | undefined,
    cross = false,
  ) =>
    from && to ? (
      <line
        key={id}
        className={cross ? "layer-binding" : "layer-relation"}
        x1={from.x}
        y1={from.y}
        x2={to.x}
        y2={to.y}
      />
    ) : null;

  return (
    <section className="ontology-overview" aria-label="已发布本体分层总览">
      <div className="overview-layer-rail" aria-label="本体层级">
        {layers.map((layer) => {
          const restricted =
            !details && (layer.id === "instance" || layer.id === "mapping");
          return (
            <div
              className={"overview-layer-item layer-" + layer.id}
              key={layer.id}
            >
              <button
                className="overview-layer-title"
                aria-pressed={active === layer.id}
                onClick={() => toggle(layer.id)}
              >
                <span className="layer-rail-dot" />
                {layer.title}
              </button>
              {layer.id === "service" && (
                <div className="overview-layer-counts">
                  <span>REST API</span>
                  <span>MCP</span>
                </div>
              )}
              {layer.id === "semantic" && (
                <div className="overview-layer-counts">
                  <span>业务对象 ({types.length})</span>
                  <span>本体关系 ({relations.length})</span>
                  <span>属性 ({graph.nodes.length - types.length})</span>
                </div>
              )}
              {restricted && (
                <span className="layer-restricted">
                  <LockKeyhole size={12} />
                  仅空间成员可见
                </span>
              )}
              {layer.id === "instance" && details && (
                <div className="overview-layer-counts">
                  <span>文档实例 ({details.object_count})</span>
                  <span>实例关系 ({details.link_count})</span>
                  <span>来源材料 ({details.evidence_material_count})</span>
                </div>
              )}
              {layer.id === "mapping" && details && (
                <div className="overview-layer-counts">
                  <span>对象映射 ({details.mapping_count})</span>
                  <span>数据库实例按需查询</span>
                </div>
              )}
              {active === layer.id && !restricted && (
                <div className="overview-layer-action">
                  {layer.id === "semantic" ? (
                    <button onClick={onSemantic}>
                      进入语义视图
                      <ArrowUpRight size={12} />
                    </button>
                  ) : layer.id === "instance" ? (
                    <Link to="../objects">
                      浏览业务对象
                      <ArrowUpRight size={12} />
                    </Link>
                  ) : details ? (
                    <Link
                      to={
                        layer.id === "mapping" ? "../mappings" : "../delivery"
                      }
                    >
                      {layer.id === "mapping" ? "管理映射" : "发布与服务"}
                      <ArrowUpRight size={12} />
                    </Link>
                  ) : null}
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div className="overview-stage">
        <svg
          viewBox="0 0 880 640"
          role="group"
          aria-label="服务、语义模型、实例与证据、数据映射四层图"
        >
          <defs>
            <pattern
              id={pattern}
              width="12"
              height="12"
              patternUnits="userSpaceOnUse"
            >
              <path d="M12 0H0V12" className="layer-grid-line" />
            </pattern>
          </defs>
          <g
            transform={
              "translate(" +
              440 * (1 - zoom) +
              " " +
              320 * (1 - zoom) +
              ") scale(" +
              zoom +
              ")"
            }
          >
            <g
              aria-hidden="true"
              className={active ? "layer-bindings is-muted" : "layer-bindings"}
            >
              {objects.map((o) =>
                line(
                  "object-" + o.id,
                  typePositions.get(o.type_id),
                  objectPositions.get(o.id),
                  true,
                ),
              )}
              {mappings.map((m) =>
                line(
                  "mapping-" + m.id,
                  typePositions.get(m.type_id),
                  mappingPositions.get(m.id),
                  true,
                ),
              )}
            </g>
            {layers.map((layer) => {
              const corners = [
                [0, 0],
                [1, 0],
                [1, 1],
                [0, 1],
              ].map(([u, v]) => point(layer, u, v));
              const points = corners.map((p) => p.x + "," + p.y).join(" ");
              const muted = active && active !== layer.id;
              return (
                <g
                  key={layer.id}
                  data-layer={layer.id}
                  className={
                    "overview-plane layer-" +
                    layer.id +
                    (muted ? " is-muted" : "")
                  }
                >
                  <polygon points={points} className="layer-plane-surface" />
                  <polygon
                    points={points}
                    fill={"url(#" + pattern + ")"}
                    className="layer-plane-grid"
                  />
                  {layer.id === "service" &&
                    ["REST API", "MCP"].map((name, i) => (
                      <g
                        key={name}
                        className="layer-service-marker"
                        transform={"translate(" + (410 + i * 118) + " 95)"}
                      >
                        <circle r="5" />
                        <text x="12" y="4">
                          {name}
                        </text>
                      </g>
                    ))}
                  {layer.id === "semantic" && (
                    <>
                      <g aria-hidden="true">
                        {relations.map((r) =>
                          line(
                            r.id,
                            typePositions.get(r.source),
                            typePositions.get(r.target),
                          ),
                        )}
                      </g>
                      {shownTypes.map((type) => {
                        const p = typePositions.get(type.id)!;
                        return (
                          <g
                            key={type.id}
                            className="layer-data-node"
                            transform={"translate(" + p.x + " " + p.y + ")"}
                            role="button"
                            tabIndex={0}
                            aria-label={"查看本体：" + type.label}
                            onClick={() =>
                              onSelect({ category: "node", item: type })
                            }
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                onSelect({ category: "node", item: type });
                              }
                            }}
                          >
                            <title>{type.label}</title>
                            <circle className="layer-hit-area" r="18" />
                            <circle r="5" />
                            {shownTypes.length <= 8 && (
                              <text x="11" y="4">
                                {type.label}
                              </text>
                            )}
                          </g>
                        );
                      })}
                      {types.length > shownTypes.length && (
                        <text
                          className="layer-empty-label"
                          x="470"
                          y={layer.y + 68}
                        >
                          概览展示 {shownTypes.length} / {types.length}{" "}
                          个对象，进入语义视图查看全部
                        </text>
                      )}
                    </>
                  )}
                  {layer.id === "instance" && (
                    <>
                      <g aria-hidden="true">
                        {details?.links.map((r) =>
                          line(
                            r.id,
                            objectPositions.get(r.source_id),
                            objectPositions.get(r.target_id),
                          ),
                        )}
                      </g>
                      {objects.map((o) => {
                        const p = objectPositions.get(o.id)!;
                        return (
                          <g
                            key={o.id}
                            className="layer-data-node"
                            transform={"translate(" + p.x + " " + p.y + ")"}
                            role="button"
                            tabIndex={0}
                            aria-label={"查看实例：" + o.name}
                            onClick={() => visitObject(o.type_id, o.id)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                visitObject(o.type_id, o.id);
                              }
                            }}
                          >
                            <title>{o.name}</title>
                            <circle className="layer-hit-area" r="18" />
                            <circle r="5" />
                            {objects.length <= 8 && (
                              <text x="11" y="4">
                                {o.name.length > 10
                                  ? o.name.slice(0, 10) + "…"
                                  : o.name}
                              </text>
                            )}
                          </g>
                        );
                      })}
                      {!objects.length && (
                        <text
                          className="layer-empty-label"
                          x="470"
                          y={layer.y + 4}
                        >
                          {details ? "暂无已发布文档实例" : "仅空间成员可见"}
                        </text>
                      )}
                      {details && details.object_count > objects.length && (
                        <text
                          className="layer-empty-label"
                          x="470"
                          y={layer.y + 78}
                        >
                          概览展示 {objects.length} / {details.object_count}{" "}
                          个实例
                        </text>
                      )}
                    </>
                  )}
                  {layer.id === "mapping" && (
                    <>
                      {mappings.map((m) => {
                        const p = mappingPositions.get(m.id)!;
                        return (
                          <g
                            key={m.id}
                            className="layer-data-node"
                            transform={"translate(" + p.x + " " + p.y + ")"}
                            role="button"
                            tabIndex={0}
                            aria-label={"查看映射：" + m.table_name}
                            onClick={() => navigate("../objects/" + m.type_id)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                navigate("../objects/" + m.type_id);
                              }
                            }}
                          >
                            <title>{m.table_name}</title>
                            <circle className="layer-hit-area" r="18" />
                            <rect x="-5" y="-5" width="10" height="10" rx="2" />
                            {mappings.length <= 8 && (
                              <text x="11" y="4">
                                {m.table_name.length > 14
                                  ? m.table_name.slice(0, 14) + "…"
                                  : m.table_name}
                              </text>
                            )}
                          </g>
                        );
                      })}
                      {!mappings.length && (
                        <text
                          className="layer-empty-label"
                          x="470"
                          y={layer.y + 4}
                        >
                          {details ? "暂无已发布数据映射" : "仅空间成员可见"}
                        </text>
                      )}
                      {details && details.mapping_count > mappings.length && (
                        <text
                          className="layer-empty-label"
                          x="470"
                          y={layer.y + 88}
                        >
                          概览展示 {mappings.length} / {details.mapping_count}{" "}
                          条映射
                        </text>
                      )}
                    </>
                  )}
                </g>
              );
            })}
          </g>
        </svg>
        <div className="overview-controls" aria-label="全局图缩放">
          <button
            className="icon-button"
            aria-label="放大全局图"
            disabled={zoom >= 1.6}
            onClick={() => setZoom((v) => Math.min(1.6, +(v + 0.2).toFixed(1)))}
          >
            <Plus size={16} />
          </button>
          <span>{Math.round(zoom * 100)}%</span>
          <button
            className="icon-button"
            aria-label="缩小全局图"
            disabled={zoom <= 0.6}
            onClick={() => setZoom((v) => Math.max(0.6, +(v - 0.2).toFixed(1)))}
          >
            <Minus size={16} />
          </button>
          <button
            className="icon-button"
            aria-label="适配全局图"
            onClick={() => {
              setZoom(1);
              setActive(null);
            }}
          >
            <Maximize size={15} />
          </button>
        </div>
      </div>
    </section>
  );
}
