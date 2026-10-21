import { App, Button, Empty, Input, Popconfirm, Select, Table, Tag, Tooltip, Typography, Upload } from "antd";
import { Archive, ArchiveRestore, Download, FileText, RefreshCw, Search, Trash2, Upload as UploadIcon } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { modelingApi } from "../api/client";
import type { ManagedMaterial, Workspace } from "../api/types";
import { useErrorMessage } from "../hooks/useErrorMessage";
import { usePageActive } from "../hooks/usePageTab";
import { PageToolbar, Panel, StatusMark } from "./layout";

const sizeText = (size: number) => size < 1024 ? `${size} B` : size < 1024 * 1024
  ? `${(size / 1024).toFixed(1)} KB` : `${(size / 1024 / 1024).toFixed(1)} MB`;

export function DocumentMaterials({ workspace }: { workspace: Workspace }) {
  const { message } = App.useApp();
  const active = usePageActive();
  const [materials, setMaterials] = useState<ManagedMaterial[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [origin, setOrigin] = useState<"upload" | "table_receipt">("upload");
  const revision = useRef(0);
  useErrorMessage(error);
  const load = useCallback(async () => {
    const request = ++revision.current;
    setError("");
    setLoading(true);
    try {
      const result = await modelingApi.materialOverview(workspace.id);
      if (request === revision.current) setMaterials(result.items);
    } catch (e) {
      if (request === revision.current) setError(e instanceof Error ? e.message : "文档读取失败");
    } finally {
      if (request === revision.current) setLoading(false);
    }
  }, [workspace.id]);
  useEffect(() => {
    const requestRevision = revision;
    if (active) void load();
    return () => { requestRevision.current++; };
  }, [load, active]);
  const upload = async (files: File[]) => {
    setBusy(true);
    setError("");
    try {
      for (const file of files) await modelingApi.upload(workspace.id, file);
      void message.success("文档已上传");
    } catch (e) {
      void message.error(e instanceof Error ? e.message : "上传失败");
    } finally {
      await load();
      setBusy(false);
    }
  };
  const remove = async (material: ManagedMaterial) => {
    setBusy(true);
    setError("");
    try {
      await modelingApi.deleteMaterial(workspace.id, material.id);
      void message.success("文档已删除");
    } catch (e) {
      void message.error(e instanceof Error ? e.message : "删除失败");
    } finally {
      await load();
      setBusy(false);
    }
  };
  const setArchived = async (material: ManagedMaterial, archived: boolean) => {
    setBusy(true);
    setError("");
    try {
      if (archived) await modelingApi.archiveMaterial(workspace.id, material.id);
      else await modelingApi.restoreMaterial(workspace.id, material.id);
      void message.success(archived ? "文档已归档" : "文档已恢复");
    } catch (e) {
      void message.error(e instanceof Error ? e.message : archived ? "归档失败" : "恢复失败");
    } finally {
      await load();
      setBusy(false);
    }
  };
  const rows = materials.filter((material) => (material.origin ?? "upload") === origin
    && material.name.toLowerCase().includes(query.trim().toLowerCase())
    && (filter === "all"
      || (filter === "archived" ? !!material.archived_at
        : filter === "unused" ? material.usage.can_delete
          : !material.usage.can_delete)));
  return <>
    <PageToolbar extra={<>
      <Select aria-label="文档来源" value={origin} onChange={setOrigin} options={[
        { value: "upload", label: "上传的文档" }, { value: "table_receipt", label: "表结构收据" },
      ]} />
      <Select aria-label="文档使用情况" value={filter} onChange={setFilter} options={[
        { value: "all", label: "全部文档" }, { value: "used", label: "已使用" }, { value: "unused", label: "未使用" },
        { value: "archived", label: "已归档" },
      ]} />
      <Input type="search" allowClear prefix={<Search size={14} />} className="w-60" aria-label="搜索文档" placeholder="搜索文档名称" value={query} onChange={(e) => setQuery(e.target.value)} />
      <Tooltip title="刷新文档"><Button aria-label="刷新文档" disabled={busy} icon={<RefreshCw size={14} />} onClick={() => void load()} /></Tooltip>
    </>}>
      <Upload accept=".md,.markdown,.txt,.json,.yaml,.yml,.csv" multiple showUploadList={false} disabled={busy}
        beforeUpload={(file, files) => { if (file === files[0]) void upload(files); return false; }}>
        <Button type="primary" icon={<UploadIcon size={14} />} loading={busy}>上传文档</Button>
      </Upload>
      <Typography.Text type="secondary" className="text-xs">{materials.filter((m) => (m.origin ?? "upload") === "upload").length} 个文档</Typography.Text>
    </PageToolbar>
    <Panel>
    <Table<ManagedMaterial> size="middle" rowKey="id" loading={loading} dataSource={rows} pagination={rows.length > 20 ? { pageSize: 20 } : false}
      locale={{ emptyText: <Empty description={error ? "文档未加载，请刷新重试" : origin === "table_receipt" && !query && filter === "all" ? "还没有表结构收据：建模运行使用已同步的表时自动生成" : query || filter !== "all" ? "没有匹配的文档" : "尚未上传文档"} /> }}
      expandable={{ expandedRowRender: (material) => <div className="flex flex-wrap items-center gap-4 text-xs text-ink-2">
        <span>属性 {material.usage.properties}</span><span>规则 {material.usage.rules}</span><span>指标 {material.usage.metrics}</span>
        <span>引用位置：{material.usage.references.join("、") || "无"}</span>
      </div> }}
      columns={[
        { title: "文档", key: "name", render: (_, material) => <div className="flex min-w-0 items-center gap-2">
          <FileText size={15} className="shrink-0 text-muted" /><span className="wrap-anywhere">{material.name}</span>
          {material.archived_at && <Tag className="m-0">已归档</Tag>}
        </div> },
        { title: <Tooltip title="历史版本、会话草稿及提案中，直接引用此文档的实体定义，按实体标识去重">实体</Tooltip>, key: "entities", render: (_, material) => material.usage.object_types },
        { title: "关系", key: "relations", render: (_, material) => material.usage.link_types },
        { title: "实体实例", key: "facts", render: (_, material) => material.usage.material_objects },
        { title: "关系实例", key: "links", render: (_, material) => material.usage.material_links },
        { title: "使用情况", key: "usage", render: (_, material) => <Tooltip title={material.usage.references.join("、") || "没有引用，可删除"}>
          <StatusMark state={material.usage.can_delete ? "unmapped" : "mapped"} label={material.usage.can_delete ? "未使用" : "已使用"} />
        </Tooltip> },
        { title: "大小", key: "size", render: (_, material) => sizeText(material.byte_size) },
        { title: "上传时间", key: "created", render: (_, material) => material.created_at ? new Date(material.created_at).toLocaleString("zh-CN", { hour12: false }) : "—" },
        { title: "操作", key: "actions", render: (_, material) => {
          const reason = workspace.role !== "admin" ? "仅空间管理员可删除文档" : !material.usage.can_delete ? `被${material.usage.references.join("、")}引用，不能删除` : "删除文档";
          const disabled = busy || workspace.role !== "admin" || !material.usage.can_delete;
          return <div className="flex items-center gap-1">
            <Tooltip title="下载文档"><Button size="small" type="text" aria-label={`下载 ${material.name}`} icon={<Download size={14} />} href={modelingApi.materialDownloadUrl(workspace.id, material.id)} /></Tooltip>
            {material.archived_at
              ? <Tooltip title="恢复文档"><Button size="small" type="text" aria-label={`恢复 ${material.name}`} disabled={busy} icon={<ArchiveRestore size={14} />} onClick={() => void setArchived(material, false)} /></Tooltip>
              : <Tooltip title="归档后不再出现在建模材料列表中，历史引用保留"><Button size="small" type="text" aria-label={`归档 ${material.name}`} disabled={busy} icon={<Archive size={14} />} onClick={() => void setArchived(material, true)} /></Tooltip>}
            <Popconfirm title="删除文档？" description={`将永久删除“${material.name}”，此操作无法撤销。`} okText="删除" okButtonProps={{ danger: true }} disabled={disabled} onConfirm={() => remove(material)}>
              <Tooltip title={reason}><span><Button size="small" type="text" danger aria-label={`删除 ${material.name}`} disabled={disabled} icon={<Trash2 size={14} />} /></span></Tooltip>
            </Popconfirm>
          </div>;
        } },
      ]} />
    </Panel>
  </>;
}
