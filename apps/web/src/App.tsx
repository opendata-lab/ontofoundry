import {
  createBrowserRouter,
  Navigate,
  RouterProvider,
} from "react-router-dom";
import { lazy, Suspense } from "react";
import { LoadingSurface } from "./components/AsyncState";
import { AppShell } from "./components/AppShell";

const WorkspaceDirectoryPage = lazy(() =>
  import("./pages/WorkspaceDirectoryPage").then((m) => ({
    default: m.WorkspaceDirectoryPage,
  })),
);
const router = createBrowserRouter([
  {
    path: "/",
    element: (
      <Suspense fallback={<LoadingSurface label="正在打开页面…" />}>
        <WorkspaceDirectoryPage />
      </Suspense>
    ),
  },
  { path: "/workspaces/:workspaceId/*", element: <AppShell /> },
  { path: "*", element: <Navigate to="/" replace /> },
]);
export function App() {
  return <RouterProvider router={router} />;
}
