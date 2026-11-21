import { lazy, Suspense, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, Bell, ChartNoAxesCombined, CircleHelp, Cloud, Database, FileBarChart2, GitFork,
  Layers3, LayoutDashboard, Menu, Moon, Settings2, ShieldCheck, Sun, Workflow } from "lucide-react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { api } from "./api";

export const routes = [
  ["/", "Overview", LayoutDashboard], ["/sources", "Data Sources", Database],
  ["/lakehouse", "Lakehouse Explorer", Layers3], ["/pipelines", "Pipeline Manager", Workflow],
  ["/quality", "Data Quality", ShieldCheck], ["/lineage", "Data Lineage", GitFork],
  ["/analytics", "Business Analytics", ChartNoAxesCombined], ["/assistant", "AI Operations Assistant", CircleHelp],
  ["/alerts", "Alerts & Monitoring", Bell], ["/infrastructure", "Cloud Infrastructure", Cloud],
  ["/reports", "Reports", FileBarChart2], ["/settings", "Settings", Settings2],
] as const;

const pages = [
  lazy(() => import("./overview")),
  lazy(() => import("./data-pages").then(({ SourcesPage }) => ({ default: SourcesPage }))),
  lazy(() => import("./data-pages").then(({ LakehousePage }) => ({ default: LakehousePage }))),
  lazy(() => import("./ops-pages").then(({ PipelinesPage }) => ({ default: PipelinesPage }))),
  lazy(() => import("./data-pages").then(({ QualityPage }) => ({ default: QualityPage }))),
  lazy(() => import("./data-pages").then(({ LineagePage }) => ({ default: LineagePage }))),
  lazy(() => import("./data-pages").then(({ AnalyticsPage }) => ({ default: AnalyticsPage }))),
  lazy(() => import("./ops-pages").then(({ AssistantPage }) => ({ default: AssistantPage }))),
  lazy(() => import("./ops-pages").then(({ AlertsPage }) => ({ default: AlertsPage }))),
  lazy(() => import("./ops-pages").then(({ InfrastructurePage }) => ({ default: InfrastructurePage }))),
  lazy(() => import("./ops-pages").then(({ ReportsPage }) => ({ default: ReportsPage }))),
  lazy(() => import("./ops-pages").then(({ SettingsPage }) => ({ default: SettingsPage }))),
];

export default function App() {
  const [theme, setTheme] = useState(() => localStorage.getItem("cloudlake-theme") ?? "dark");
  const [menu, setMenu] = useState(false);
  const location = useLocation();
  const status = useQuery({ queryKey: ["system"], queryFn: () => api<{api: string}>("/system/status"), refetchInterval: 20_000 });
  document.documentElement.dataset.theme = theme;
  const current = routes.find(([path]) => path === location.pathname)?.[1] ?? "CloudLake AI";
  return (
    <div className="shell">
      <aside className={menu ? "sidebar open" : "sidebar"}>
        <NavLink to="/" className="brand" onClick={() => setMenu(false)}><Layers3 size={20} /> CloudLake AI</NavLink>
        <nav aria-label="Primary">
          {routes.map(([path, name, Icon]) => <NavLink key={path} to={path} end onClick={() => setMenu(false)}><Icon size={17} /> {name}</NavLink>)}
        </nav>
        <div className="workspace"><Database size={16} /><div>Local workspace<small>Synthetic commerce data</small></div></div>
      </aside>
      <div className="body">
        <header className="topbar">
          <button className="menu icon" aria-label="Toggle navigation" onClick={() => setMenu(!menu)}><Menu size={19} /></button>
          <span className="breadcrumb">Workspace <span>/</span> {current}</span>
          <span className="connection"><Activity size={15} /> {status.isPending ? "Connecting" : status.isError ? "API unavailable" : "API connected"}</span>
          <button className="icon" aria-label="Toggle color theme" onClick={() => {
            const next = theme === "dark" ? "light" : "dark";
            localStorage.setItem("cloudlake-theme", next);
            setTheme(next);
          }}>{theme === "dark" ? <Sun size={18}/> : <Moon size={18}/>}</button>
        </header>
        <main>
          <Suspense fallback={<div className="panel empty" role="status">Loading workspace page</div>}><Routes>
            {routes.map(([path], index) => {
              const Page = pages[index];
              return <Route key={path} path={path} element={<Page />} />;
            })}
            <Route path="*" element={<h1>Page unavailable</h1>} />
          </Routes></Suspense>
        </main>
      </div>
    </div>
  );
}
