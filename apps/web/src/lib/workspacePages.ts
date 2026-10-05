/**
 * The workspace pages' code, loaded on demand. A route change renders inside
 * a transition, so a page whose code is still downloading keeps the previous
 * page on screen with no feedback. Fetching the rest while the browser is idle
 * makes a later menu click switch at once.
 */
export const pageLoaders = {
  BuilderPage: () => import("../pages/BuilderPage"),
  OntologyViewPage: () => import("../pages/OntologyViewPage"),
  TypeCatalogPage: () => import("../pages/TypeCatalogPage"),
  ObjectDetailPage: () => import("../pages/ObjectDetailPage"),
  ObjectEditorPage: () => import("../pages/ObjectEditorPage"),
  ConnectionsPage: () => import("../pages/ConnectionsPage"),
  MappingsPage: () => import("../pages/MappingsPage"),
  InstancesPage: () => import("../pages/InstancesPage"),
  DeliveryPage: () => import("../pages/DeliveryPage"),
  SettingsPage: () => import("../pages/SettingsPage"),
};

export function preloadWorkspacePages() {
  const run = () => Object.values(pageLoaders).forEach((load) => void load().catch(() => undefined));
  if (typeof window.requestIdleCallback === "function") window.requestIdleCallback(run, { timeout: 3000 });
  else window.setTimeout(run, 1500);
}
