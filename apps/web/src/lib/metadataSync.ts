import { catalogApi } from "../api/client";
import type { Assets } from "../api/types";

export const METADATA_SYNCED = "ontofoundry:metadata-synced";
export const syncTime = (time?: string | null) => time ? new Date(time).toLocaleString("zh-CN", { hour12: false }) : "尚未同步";
export type SchemaAssets = { schema: string; assets: Assets };
/** Synced tables grouped by schema, read from the platform without opening the source. */
export async function loadSchemaAssets(workspaceId: string, connectionId: string): Promise<SchemaAssets[]> {
  return (await catalogApi.syncedAssets(workspaceId, connectionId)).items;
}
