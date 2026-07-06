import { lazy } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { ProtectedRoute } from "@/auth/ProtectedRoute";
import { LoginPage } from "@/pages/LoginPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { AttendancePage } from "@/pages/AttendancePage";
import { ReportsPage } from "@/pages/ReportsPage";
import { RosterPage } from "@/pages/RosterPage";
import { DriversPage } from "@/pages/DriversPage";
import { AuditPage } from "@/pages/AuditPage";
import { MenusPage } from "@/pages/MenusPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { NotFoundPage } from "@/pages/NotFoundPage";

// Leaflet-heavy pages are code-split so the map bundle loads on demand.
const TrackingPage = lazy(() =>
  import("@/pages/TrackingPage").then((m) => ({ default: m.TrackingPage })),
);
const RoutesPage = lazy(() =>
  import("@/pages/RoutesPage").then((m) => ({ default: m.RoutesPage })),
);

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    element: <ProtectedRoute />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { index: true, element: <DashboardPage /> },
          { path: "tracking", element: <TrackingPage /> },
          { path: "attendance", element: <AttendancePage /> },
          { path: "reports", element: <ReportsPage /> },
          { path: "roster", element: <RosterPage /> },
          { path: "routes", element: <RoutesPage /> },
          { path: "drivers", element: <DriversPage /> },
          { path: "audit", element: <AuditPage /> },
          { path: "menus", element: <MenusPage /> },
          { path: "settings", element: <SettingsPage /> },
          { path: "404", element: <NotFoundPage /> },
          { path: "*", element: <Navigate to="/404" replace /> },
        ],
      },
    ],
  },
]);
