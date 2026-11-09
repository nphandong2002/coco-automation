import { NavLink, Outlet } from "react-router-dom";
import { Toaster } from "./ui";

/** Modules from later phases are listed but disabled until implemented (no fake screens). */
const NAV: { to: string; label: string; icon: string; phase?: number }[] = [
  { to: "/", label: "Overview", icon: "◎" },
  { to: "/channels", label: "Channels", icon: "▶" },
  { to: "/characters", label: "Characters", icon: "☺" },
  { to: "/content", label: "Content Library", icon: "▤" },
  { to: "/production", label: "Video Production", icon: "◧" },
  { to: "/assets", label: "Assets", icon: "▣" },
  { to: "/publishing", label: "Publishing", icon: "↑" },
  { to: "/scheduler", label: "Scheduler", icon: "◷" },
  { to: "/analytics", label: "Analytics", icon: "▲" },
  { to: "/monitoring", label: "Monitoring", icon: "♥" },
  { to: "/settings", label: "System Settings", icon: "⚙" },
];

export default function Layout() {
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-brand-100 bg-white md:flex">
        <div className="px-5 py-5">
          <div className="text-lg font-bold">☕ Coco Automation</div>
          <div className="text-xs text-ink-500">Multi-channel YouTube platform</div>
        </div>
        <nav className="flex-1 space-y-0.5 px-3">
          {NAV.map((n) =>
            n.phase ? (
              <div key={n.to} title={`Sẽ có ở Phase ${n.phase}`}
                className="flex cursor-not-allowed items-center gap-3 rounded-lg px-3 py-2 text-sm text-ink-300">
                <span className="w-4 text-center">{n.icon}</span>{n.label}
                <span className="ml-auto rounded bg-slate-100 px-1.5 text-[10px] text-slate-500">P{n.phase}</span>
              </div>
            ) : (
              <NavLink key={n.to} to={n.to} end={n.to === "/"}
                className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium ${isActive ? "bg-brand-100 text-brand-700" : "text-ink-700 hover:bg-brand-50"}`}>
                <span className="w-4 text-center">{n.icon}</span>{n.label}
              </NavLink>
            ),
          )}
        </nav>
        <div className="px-5 py-4 text-xs text-ink-500">Phase 5 · v0.5.0</div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 overflow-x-auto border-b border-brand-100 bg-white px-4 py-2 md:hidden">
          {NAV.filter((n) => !n.phase).map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/"} className={({ isActive }) => `whitespace-nowrap text-sm ${isActive ? "font-semibold text-brand-700" : "text-ink-500"}`}>{n.label}</NavLink>
          ))}
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 p-4 md:p-8"><Outlet /></main>
      </div>
      <Toaster />
    </div>
  );
}
