/** Index only published immutable collections; edited arrays are never memoized. */
const published = new WeakSet<object>();
const indexes = new WeakMap<object, Map<string, unknown>>();
const groups = new WeakMap<object, Map<string, Map<string, unknown[]>>>();
export function registerDefinitions(model: object) {
  Object.values(model).forEach(value => { if (Array.isArray(value)) published.add(value); });
}
export function indexedById<T extends { id: string }>(items: T[], id: string): T | undefined {
  if (!published.has(items)) return items.find(item => item.id === id);
  let index = indexes.get(items);
  if (!index) { index = new Map(items.map(item => [item.id, item])); indexes.set(items, index); }
  return index.get(id) as T | undefined;
}
export function owned<T, K extends keyof T>(items: T[], key: K, id: T[K]): T[] {
  if (!published.has(items)) return items.filter(item => item[key] === id);
  let fields = groups.get(items);
  if (!fields) { fields = new Map(); groups.set(items, fields); }
  let index = fields.get(String(key));
  if (!index) {
    index = new Map();
    for (const item of items) {
      const identity = String(item[key]);
      const group = index.get(identity) ?? [];
      group.push(item); index.set(identity, group);
    }
    fields.set(String(key), index);
  }
  return [...(index.get(String(id)) ?? [])] as T[];
}
