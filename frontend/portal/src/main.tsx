import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import "./styles/theme.css";
import "./styles/layout.css";

import {
  AuthProvider, canAdmin, canAudit, canReview, canRunSim, canSubmit, isStaff, useAuth,
} from "./auth";
import type { Role } from "./api/client";
import Shell from "./components/Shell";
import Login from "./pages/Login";
import Overview from "./pages/Overview";
import Console from "./pages/Console";
import Publications from "./pages/Publications";
import IsrReport from "./pages/IsrReport";
import MyArea from "./pages/MyArea";
import Alerts from "./pages/Alerts";
import Methods from "./pages/Methods";
import FieldData from "./pages/FieldData";
import DataGaps from "./pages/DataGaps";
import Audit from "./pages/Audit";
import Administration from "./pages/Administration";
import PublicView from "./pages/PublicView";

const qc = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});

/**
 * Client-side route guard.
 *
 * A convenience, not a boundary: it stops a user landing on a screen that would
 * only 403, and keeps a stray URL from rendering an empty shell. The real
 * enforcement is the API guard and the RLS policy behind it — this cannot be
 * the thing that protects site coordinates.
 */
function Guard({ allow, children }: { allow: (r?: Role) => boolean; children: React.ReactNode }) {
  const { me } = useAuth();
  if (!allow(me?.role)) {
    return (
      <div className="page">
        <div className="banner danger">
          <strong>Not available for your role.</strong> This section is restricted, and
          the API would refuse the request regardless of what this page rendered.
        </div>
      </div>
    );
  }
  return <>{children}</>;
}

function Gate() {
  const { me, loading } = useAuth();
  if (loading) {
    return <div className="login"><span className="spinner" /></div>;
  }
  if (!me) return <Login />;

  return (
    <Routes>
      <Route element={<Shell />}>
        <Route path="/overview" element={<Overview />} />
        {/* P2 merged /map and /studio into one Console. The old paths redirect
            rather than 404: they were linked from the role overviews and are
            almost certainly bookmarked. */}
        <Route path="/console" element={<Guard allow={isStaff}><Console /></Guard>} />
        <Route
          path="/publications"
          element={<Guard allow={(r) => canRunSim(r) || canReview(r)}><Publications /></Guard>}
        />
        {/* The full assessment record for one site. Staff-readable: it carries
            the site's coordinates and operating parameters, which design §2
            keeps away from the public surface. */}
        <Route path="/report/:siteId"
               element={<Guard allow={isStaff}><IsrReport /></Guard>} />
        <Route path="/map" element={<Navigate to="/console" replace />} />
        <Route path="/studio" element={<Navigate to="/console" replace />} />
        <Route
          path="/field"
          element={<Guard allow={(r) => canSubmit(r) || canReview(r)}><FieldData /></Guard>}
        />
        <Route path="/data" element={<Guard allow={isStaff}><DataGaps /></Guard>} />
        <Route path="/audit" element={<Guard allow={canAudit}><Audit /></Guard>} />
        <Route path="/admin" element={<Guard allow={canAdmin}><Administration /></Guard>} />
        {/* The citizen surface. Every signed-in role may read these: an
            official seeing exactly what a resident sees is a feature, and
            nothing here is restricted. */}
        <Route path="/my-area" element={<MyArea />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/methods" element={<Methods />} />
        {/* The old map-and-table public view, kept for staff review. */}
        <Route path="/public" element={<PublicView />} />
        <Route path="*" element={<Navigate to="/overview" replace />} />
      </Route>
    </Routes>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <AuthProvider>
          <Gate />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
