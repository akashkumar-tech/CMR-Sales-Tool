import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "@/lib/api";
import { stageStyle, fmtDate } from "@/lib/crm";
import { useAutoRefresh } from "@/lib/useAutoRefresh";
import LeadDrawer from "@/components/LeadDrawer";
import { Card } from "@/components/ui/card";
import { Calendar, User, Clock } from "lucide-react";

// Values of GET /leads?demo= (DEMO_FILTERS in server.py). "all" = every lead with a booked demo — the same rule
// (lead_has_demo) the Reports "Demos" count uses.
const DEMO_FILTERS = [
  ["all", "All demos"],
  ["booked", "Demo Booked"],
  ["not_complete", "Demo Booked but Not Complete"],
  ["no_show", "Demo Booked but No Show"],
  ["not_paid", "Demo Booked but Not Paid"],
  ["rescheduled", "Demo Booked but Rescheduled"],
  ["completed", "Demo Completed"],
];
const FILTER_KEYS = DEMO_FILTERS.map(([k]) => k);
// Leads without a demo status: the outcome their stage implies (same fallback the backend filters use).
const STAGE_DEMO_STATUS = { "Demo Completed": "Completed", "Demo No-show": "No-show", "Rescheduled": "Rescheduled" };

export default function Demos() {
  const [leads, setLeads] = useState([]);
  const [members, setMembers] = useState([]);
  const [selected, setSelected] = useState(null);
  const [open, setOpen] = useState(false);
  const [params, setParams] = useSearchParams();
  const filter = FILTER_KEYS.includes(params.get("demo")) ? params.get("demo") : "all";
  const setFilter = (v) => setParams((sp) => { if (v === "all") sp.delete("demo"); else sp.set("demo", v); return sp; }, { replace: true });

  // Filtered by the backend, so the list is exactly the leads that match (and respects role scoping).
  const load = useCallback(() => api.get("/leads", { params: { demo: filter } }).then((r) => setLeads(r.data)).catch(() => {}), [filter]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.get("/users").then((r) => setMembers(r.data)).catch(() => {}); }, []);
  useAutoRefresh(load, 10000);
  const memberName = (id) => members.find((m) => m.id === id)?.name || "Unassigned";

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div><p className="text-[11px] font-bold uppercase tracking-[0.16em] text-primary">Demos</p><h1 className="text-3xl font-extrabold tracking-tight text-slate-900">Demo Pipeline</h1></div>
        <div className="flex items-center gap-2">
          <select data-testid="demo-filter-select" aria-label="Filter demos" value={filter} onChange={(e) => setFilter(e.target.value)} className="h-9 rounded-lg border border-border text-sm px-3 text-slate-600">
            {DEMO_FILTERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          {filter !== "all" && <button data-testid="demo-filter-clear" onClick={() => setFilter("all")} className="text-xs font-semibold text-primary hover:underline">Clear</button>}
          <span data-testid="demo-count" className="text-xs text-slate-500">{leads.length} lead{leads.length === 1 ? "" : "s"}</span>
        </div>
      </div>
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
        {leads.map((l) => (
          <Card key={l.id} data-testid={`demo-card-${l.id}`} onClick={() => { setSelected(l.id); setOpen(true); }} className="p-5 cursor-pointer hover:-translate-y-0.5 transition-transform">
            <div className="flex items-center justify-between">
              <span className={`px-2 py-0.5 rounded-full text-xs font-semibold border ${stageStyle(l.status)}`}>{l.status}</span>
              <span className="text-xs px-2 py-0.5 rounded-full bg-purple-50 text-purple-700 border border-purple-100">{l.demo_status || STAGE_DEMO_STATUS[l.status] || (l.demo_completed_at ? "Completed" : "Scheduled")}</span>
            </div>
            <p className="font-bold text-slate-900 mt-3">{l.name}</p>
            <p className="text-sm text-slate-500">{l.practice}</p>
            <div className="mt-3 space-y-1 text-xs text-slate-500">
              <p className="flex items-center gap-1.5"><Calendar size={13} /> {fmtDate(l.demo_date)}{l.demo_time ? <span className="inline-flex items-center gap-1 ml-1"><Clock size={12} /> {l.demo_time}</span> : null}</p>
              <p className="flex items-center gap-1.5"><User size={13} /> {memberName(l.demo_owner)}</p>
            </div>
          </Card>
        ))}
        {leads.length === 0 && <p className="text-sm text-slate-400 col-span-full text-center py-8">{filter === "all" ? "No demos scheduled." : "No demos match this filter."}</p>}
      </div>
      <LeadDrawer leadId={selected} open={open} onOpenChange={setOpen} onChange={load} members={members} initialTab="demo" />
    </div>
  );
}
