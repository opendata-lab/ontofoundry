import { catalogApi } from "../api/client";
import type { Assets } from "../api/types";

export const METADATA_SYNCED = "ontofoundry:metadata-synced";
export const syncTime = (time?: string | null) => time ? new Date(time).toLocaleString("zh-CN", { hour12: false }) : "尚未同步";
export type SchemaAssets = { schema: string; assets: Assets };
export async function loadSchemaAssets(workspaceId: string, connectionId: string): Promise<SchemaAssets[]> {
  const { items } = await catalogApi.schemas(workspaceId, connectionId);
  return Promise.all(items.map(async (schema) => ({ schema, assets: await catalogApi.assets(workspaceId, connectionId, { schema_name: schema }) })));
}

