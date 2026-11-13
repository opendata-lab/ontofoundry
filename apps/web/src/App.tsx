import {
  createBrowserRouter,
  Navigate,
  RouterProvider,
} from "react-router-dom";
import { lazy, Suspense } from "react";
import { LoadingSurface, RouteErrorSurface } from "./components/AsyncState";
import { AppShell } from "./components/AppShell";
import { LoginPage } from "./pages/LoginPage";

const WorkspaceDirectoryPage = lazy(() =>
  import("./pages/WorkspaceDirectoryPage").then((m) => ({
    default: m.WorkspaceDirectoryPage,
  })),
);
const MePage = lazy(() =>
  import("./pages/MePage").then((m) => ({
    default: m.MePage,
  })),
);
const AdminUsersPage = lazy(() =>
  import("./pages/AdminUsersPage").then((m) => ({
    default: m.AdminUsersPage,
  })),
);
const AdminAuditPage = lazy(() =>
  import("./pages/AdminAuditPage").then((m) => ({
    default: m.AdminAuditPage,
  })),
);
const router = createBrowserRouter([
  {
    errorElement: <RouteErrorSurface />,
    children: [
      {
        path: "/",
        element: (
          <Suspense fallback={<LoadingSurface label="正在打开页面…" />}>
            <WorkspaceDirectoryPage />
          </Suspense>
        ),
      },
      {
        path: "/me",
        element: (
          <Suspense fallback={<LoadingSurface label="正在打开页面…" />}>
            <MePage />
          </Suspense>
        ),
      },
      {
        path: "/me/tokens",
        element: (
          <Suspense fallback={<LoadingSurface label="正在打开页面…" />}>
            <MePage />
          </Suspense>
        ),
      },
      {
        path: "/admin/users",
        element: (
          <Suspense fallback={<LoadingSurface label="正在打开页面…" />}>
            <AdminUsersPage />
          </Suspense>
        ),
      },
      {
        path: "/admin/audit",
        element: (
          <Suspense fallback={<LoadingSurface label="正在打开页面…" />}>
            <AdminAuditPage />
          </Suspense>
        ),
      },
      { path: "/login", element: <LoginPage /> },
      { path: "/workspaces/:workspaceId/*", element: <AppShell /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);
export function App() {
  return <RouterProvider router={router} />;
}
