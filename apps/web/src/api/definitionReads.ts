import { registerDefinitions } from "../lib/definitionIndex";
import type { Presentation } from "./types";

/** Process-local immutable definitions, scoped to the authenticated UI lifecycle. */
export class DefinitionReads {
  private entries = new Map<string, { promise: Promise<Presentation>; bytes: number }>();
  private permissions = new Map<string, string>();
  private projections = new Map<string, string>();
  private subject = "";
  private generation = 0;
  constructor(private budget = 32 * 1024 * 1024, private limit = 32) {}

  authorize(subject: string, workspaceId: string, permission: string) {
    if (subject !== this.subject || (this.permissions.has(workspaceId) && this.permissions.get(workspaceId) !== permission)) this.clear();
    this.subject = subject;
    this.permissions.set(workspaceId, permission);
  }
  authorizeProjection(workspaceId: string, permission: string) {
    if (this.projections.has(workspaceId) && this.projections.get(workspaceId) !== permission) this.clear();
    this.projections.set(workspaceId, permission);
  }
  clear() {
    this.generation++;
    this.entries.clear();
    this.permissions.clear();
    this.projections.clear();
  }
  peek(workspaceId: string, versionId: string): Promise<Presentation> | undefined {
    const key = this.key(workspaceId, versionId);
    const entry = this.entries.get(key);
    if (entry) { this.entries.delete(key); this.entries.set(key, entry); }
    return entry?.promise;
  }
  private key(workspaceId: string, versionId: string) {
    return JSON.stringify([this.subject, this.generation, workspaceId, versionId, this.permissions.get(workspaceId), this.projections.get(workspaceId), "presentation-1"]);
  }
  get(workspaceId: string, versionId: string, read: () => Promise<Presentation>): Promise<Presentation> {
    const key = this.key(workspaceId, versionId);
    const hit = this.entries.get(key);
    if (hit) {
      this.entries.delete(key);
      this.entries.set(key, hit);
      return hit.promise;
    }
    const generation = this.generation;
    const entry = { bytes: 0, promise: Promise.resolve(null as unknown as Presentation) };
    entry.promise = read().then(value => {
      if (generation !== this.generation) throw new Error("授权已变化，请重新读取");
      // UTF-16 strings, object overhead and indexes are estimated, not a heap limit.
      entry.bytes = JSON.stringify(value).length * 4;
      registerDefinitions(value.model);
      if (import.meta.env.DEV) freeze(value);
      this.trim();
      return value;
    }).catch(error => {
      if (this.entries.get(key) === entry) this.entries.delete(key);
      throw error;
    });
    this.entries.set(key, entry);
    return entry.promise;
  }
  stats() {
    return { entries: this.entries.size, estimatedBytes: [...this.entries.values()].reduce((sum, e) => sum + e.bytes, 0) };
  }
  private trim() {
    for (const [key, entry] of this.entries) {
      const stats = this.stats();
      if (stats.entries <= this.limit && stats.estimatedBytes <= this.budget) break;
      // Pending computations remain shared until they settle.
      if (entry.bytes) this.entries.delete(key);
    }
  }
}
function freeze(value: unknown) {
  if (!value || typeof value !== "object" || Object.isFrozen(value)) return;
  Object.freeze(value);
  Object.values(value).forEach(freeze);
}
export const definitionReads = new DefinitionReads();
