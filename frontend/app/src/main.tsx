import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import "./styles/tokens.css";
import "./styles/app.css";

import { AuthProvider, useAuth } from "./auth";
import Shell from "./components/Shell";
import Login from "./pages/Login";
import MapConsole from "./pages/MapConsole";
import SiteRegistry from "./pages/SiteRegistry";
import ReviewQueue from "./pages/ReviewQueue";

const qc = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});

function Gate() {
  const { me, loading } = useAuth();
  if (loading) {
    return (
      <div className="login-wrap">
        <span className="spinner" />
      </div>
    );
  }
  if (!me) return <Login />;
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route path="/map" element={<MapConsole />} />
        <Route path="/sites" element={<SiteRegistry />} />
        <Route path="/review" element={<ReviewQueue />} />
        <Route path="*" element={<Navigate to="/map" replace />} />
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
