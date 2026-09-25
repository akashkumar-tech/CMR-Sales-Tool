import { useEffect, useRef, useState } from "react";
import { NavLink, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { initials, stageStyle } from "@/lib/crm";
import AddLeadDialog from "@/components/AddLeadDialog";
import LeadDrawer from "@/components/LeadDrawer";
import NotificationBell from "@/components/NotificationBell";
import { Button } from "@/components/ui/button";
import {
  LayoutDashboard, Users, Building2, Kanban as KanbanIcon, CheckSquare, Activity,
  Calendar, CalendarDays, Gauge, BarChart3, PieChart, Settings as SettingsIcon, LogOut, Plus, Leaf, Search, RefreshCw,
} from "lucide-react";

const NAV = [
  { name: "Dashboard", path: "/dashboard", icon: LayoutDashboard, testid: "nav-dashboard" },
  { name: "My Leads", path: "/my-leads", icon: Users, testid: "nav-my-leads" },
  { name: "All Leads", path: "/all-leads", icon: Building2, testid: "nav-all-leads", manager: true },
  { name: "Kanban", path: "/kanban", icon: KanbanIcon, testid: "nav-kanban" },
  { name: "Calendar", path: "/calendar", icon: CalendarDays, testid: "nav-calendar" },
  { name: "Tasks", path: "/tasks", icon: CheckSquare, testid: "nav-tasks" },
  { name: "Activities", path: "/activities", icon: Activity, testid: "nav-activities" },
  { name: "Demos", path: "/demos", icon: Calendar, testid: "nav-demos" },
  { name: "Follow-ups", path: "/followups", icon: RefreshCw, testid: "nav-followups" },
  { name: "Team Workload", path: "/workload", icon: Gauge, testid: "nav-workload", manager: true },
  { name: "Team Performance", path: "/team-performance", icon: BarChart3, testid: "nav-team-performance", manager: true },
  { name: "Reports", path: "/reports", icon: PieChart, testid: "nav-reports" },
  { name: "Settings", path: "/settings", icon: SettingsIcon, testid: "nav-settings" },
];

export default function Layout({ children }) {
  const { user, logout, isManager } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [addOpen, setAddOpen] = useState(false);
  const [q, setQ] = useState("");
  const [results, setResults] = useState(null);
  const [openLeadId, setOpenLeadId] = useState(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [members, setMembers] = useState([]);
  const boxRef = useRef();

  useEffect(() => { api.get("/users").then((r) => setMembers(r.data)).catch(() => {}); }, []);

  // Deep-link: /any?open=<leadId> (from notifications / emails) opens the lead drawer.
  useEffect(() => {
    const openId = params.get("open");
    if (openId) {
      setOpenLeadId(openId); setDrawerOpen(true);
      setParams((sp) => { sp.delete("open"); return sp; }, { replace: true });
    }
  }, [params]);

  useEffect(() => {
    if (!q || q.length < 2) { setResults(null); return; }
    // A failed lookup must not read as "no duplicate" — show it as an error instead.
    const t = setTimeout(() => api.get(`/leads/search?q=${encodeURIComponent(q)}`).then((r) => setResults(r.data)).catch(() => setResults("error")), 250);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    const h = (e) => { if (boxRef.current && !boxRef.current.contains(e.target)) setResults(null); };
    document.addEventListener("mousedown", h); return () => document.removeEventListener("mousedown", h);
  }, []);

  const openResult = (id) => { setOpenLeadId(id); setDrawerOpen(true); setResults(null); setQ(""); };

  return (
    <div className="min-h-screen flex bg-background">
      <aside className="w-64 shrink-0 border-r border-border bg-white flex flex-col fixed h-screen z-40">
        <div className="h-16 flex items-center gap-2 px-6 border-b border-border">
          <div className="h-8 w-8 rounded-lg grid place-items-center text-white brand-gradient"><Leaf size={18} /></div>
          <span className="font-extrabold text-lg tracking-tight text-slate-900">Beet.Health</span>
        </div>
        <nav className="flex-1 p-3 space-y-1 overflow-y-auto scrollbar-thin">
          {NAV.filter((n) => !n.manager || isManager).map((n) => (
            <NavLink key={n.path} to={n.path} data-testid={n.testid}
              className={({ isActive }) => `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${isActive ? "bg-accent text-accent-foreground" : "text-slate-600 hover:bg-slate-50"}`}>
              <n.icon size={18} /> {n.name}
            </NavLink>
          ))}
        </nav>
        <div className="p-3 border-t border-border">
          <div className="flex items-center gap-3 px-2 py-2">
            <div className="h-9 w-9 rounded-full bg-primary/10 text-primary grid place-items-center text-sm font-bold">{initials(user?.name)}</div>
            <div className="min-w-0 flex-1"><p className="text-sm font-semibold text-slate-900 truncate">{user?.name}</p><p className="text-xs text-slate-500 capitalize">{user?.role}</p></div>
            <button data-testid="logout-btn" onClick={() => { logout(); navigate("/login"); }} className="text-slate-400 hover:text-destructive"><LogOut size={18} /></button>
          </div>
        </div>
      </aside>

      {/* min-w-0: let wide tables scroll inside their own box instead of stretching the page under the sidebar */}
      <div className="flex-1 min-w-0 ml-64 flex flex-col min-h-screen">
        <header className="h-16 sticky top-0 z-30 backdrop-blur-md bg-white/90 border-b border-border flex items-center justify-between px-6 gap-4">
          <div ref={boxRef} className="relative flex-1 max-w-md">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input data-testid="global-search-input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find any lead by name, phone, email, IG, LinkedIn…"
              className="w-full pl-9 pr-3 py-2 rounded-lg border border-border bg-slate-50 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
            {results !== null && (
              <div className="absolute top-11 left-0 right-0 bg-white border border-border rounded-lg shadow-lg max-h-80 overflow-y-auto z-50">
                {results === "error" ? <p className="p-3 text-sm text-rose-600">Search failed — please try again before adding a new lead.</p>
                  : results.length === 0 ? <p className="p-3 text-sm text-slate-400">No matching contact — safe to add as new.</p> : results.map((r) => (
                  <button key={r.id} data-testid={`search-result-${r.id}`} onClick={() => openResult(r.id)} className="w-full text-left p-3 hover:bg-slate-50 border-b border-border last:border-0">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-semibold text-slate-900">{r.name}</span>
                      <span className={`text-[11px] px-2 py-0.5 rounded-full border ${stageStyle(r.status)}`}>{r.status}</span>
                    </div>
                    <p className="text-xs text-slate-500">{r.phone || r.email} · owner: {r.owner_name}{r.last_contacted_by ? ` · last by ${r.last_contacted_by}` : ""}</p>
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="flex items-center gap-3">
            <NotificationBell />
            <span className={`px-2.5 py-1 rounded-full text-xs font-bold capitalize ${isManager ? "bg-primary/10 text-primary" : "bg-teal-50 text-teal-700"}`}>{user?.role} view</span>
            <Button data-testid="quick-add-lead-btn" onClick={() => setAddOpen(true)} className="gap-2"><Plus size={16} /> New Lead</Button>
          </div>
        </header>
        <main className="flex-1 p-6 max-w-[1500px] w-full">{children}</main>
      </div>

      <AddLeadDialog open={addOpen} onOpenChange={setAddOpen} members={members} onCreated={(id) => { if (id) { setOpenLeadId(id); setDrawerOpen(true); } }} />
      <LeadDrawer leadId={openLeadId} open={drawerOpen} onOpenChange={setDrawerOpen} members={members} onChange={() => {}} />
    </div>
  );
}
