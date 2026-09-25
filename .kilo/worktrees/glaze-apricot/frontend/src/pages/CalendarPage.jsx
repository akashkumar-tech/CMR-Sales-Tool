import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useAutoRefresh } from "@/lib/useAutoRefresh";
import LeadDrawer from "@/components/LeadDrawer";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, Calendar as CalIcon, RefreshCw, CheckSquare } from "lucide-react";

const KIND = {
  demo: { label: "Demo", chip: "bg-purple-100 text-purple-700 border-purple-200", dot: "bg-purple-500" },
  followup: { label: "Follow-up", chip: "bg-amber-100 text-amber-800 border-amber-200", dot: "bg-amber-500" },
  task: { label: "Task", chip: "bg-primary/10 text-primary border-primary/20", dot: "bg-primary" },
};
// Local calendar date (toISOString() would convert local midnight to UTC and shift every cell by a day east of UTC).
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export default function CalendarPage() {
  const { user, isManager } = useAuth();
  const [cursor, setCursor] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); });
  const [events, setEvents] = useState([]);
  const [members, setMembers] = useState([]);
  const [employee, setEmployee] = useState("all");
  const [selected, setSelected] = useState(null);
  const [open, setOpen] = useState(false);

  const grid = useMemo(() => {
    const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
    const startPad = first.getDay();
    const start = new Date(first); start.setDate(first.getDate() - startPad);
    const days = [];
    for (let i = 0; i < 42; i++) { const d = new Date(start); d.setDate(start.getDate() + i); days.push(d); }
    return days;
  }, [cursor]);

  const load = useCallback(() => {
    const start = iso(grid[0]); const end = iso(grid[41]);
    const p = new URLSearchParams({ start, end });
    if (isManager && employee !== "all") p.set("employee", employee);
    api.get(`/calendar?${p.toString()}`).then((r) => setEvents(r.data.events)).catch(() => {});
  }, [grid, employee, isManager]);
  useEffect(() => { load(); }, [load]);
  useAutoRefresh(load, 12000);
  // Everyone needs the team directory (lead drawer assignee lists); managers also use it for the filter.
  useEffect(() => { api.get("/users").then((r) => setMembers(r.data)).catch(() => {}); }, []);
  const staff = members.filter((u) => u.role !== "admin");

  const byDay = useMemo(() => {
    const m = {};
    events.forEach((e) => { (m[e.date] = m[e.date] || []).push(e); });
    Object.values(m).forEach((list) => list.sort((a, b) => (a.time || "99").localeCompare(b.time || "99")));
    return m;
  }, [events]);

  const todayISO = iso(new Date());
  const openEvent = (e) => { if (e.lead_id) { setSelected(e.lead_id); setOpen(true); } };
  const shift = (n) => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + n, 1));

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-primary">Schedule</p>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-900">Calendar</h1>
          <p className="text-sm text-slate-500 mt-1">{isManager ? "Your team's demos, follow-ups and tasks. Click any item to open the lead." : "Your demos, follow-ups and tasks. Click any item to open the lead."}</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {isManager && staff.length > 0 && (
            <select data-testid="calendar-employee-select" value={employee} onChange={(e) => setEmployee(e.target.value)} className="h-9 rounded-lg border border-border text-sm px-2 text-slate-600">
              <option value="all">Whole team</option>
              {staff.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          )}
          <Button variant="outline" size="sm" onClick={() => setCursor(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); })} data-testid="calendar-today-btn">Today</Button>
          <div className="flex items-center gap-1">
            <Button variant="outline" size="icon" className="h-9 w-9" onClick={() => shift(-1)} data-testid="calendar-prev-btn"><ChevronLeft size={16} /></Button>
            <span className="w-40 text-center font-bold text-slate-900" data-testid="calendar-month-label">{MONTHS[cursor.getMonth()]} {cursor.getFullYear()}</span>
            <Button variant="outline" size="icon" className="h-9 w-9" onClick={() => shift(1)} data-testid="calendar-next-btn"><ChevronRight size={16} /></Button>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-4 text-xs text-slate-500">
        {Object.entries(KIND).map(([k, v]) => <span key={k} className="inline-flex items-center gap-1.5"><span className={`h-2.5 w-2.5 rounded-full ${v.dot}`} /> {v.label}</span>)}
      </div>

      <Card className="overflow-hidden">
        <div className="grid grid-cols-7 bg-slate-50 border-b border-border">
          {DOW.map((d) => <div key={d} className="px-2 py-2 text-[11px] font-bold uppercase tracking-wide text-slate-400 text-center">{d}</div>)}
        </div>
        <div className="grid grid-cols-7">
          {grid.map((d, i) => {
            const key = iso(d);
            const inMonth = d.getMonth() === cursor.getMonth();
            const list = byDay[key] || [];
            return (
              <div key={i} data-testid={`cal-day-${key}`} className={`min-h-[104px] border-b border-r border-border p-1.5 ${inMonth ? "bg-white" : "bg-slate-50/60"}`}>
                <div className={`text-xs font-semibold mb-1 h-6 w-6 grid place-items-center rounded-full ${key === todayISO ? "bg-primary text-white" : inMonth ? "text-slate-600" : "text-slate-300"}`}>{d.getDate()}</div>
                <div className="space-y-1">
                  {list.slice(0, 3).map((e, j) => {
                    const k = KIND[e.kind];
                    return (
                      <button key={j} data-testid={`cal-event-${e.kind}-${e.lead_id || j}`} onClick={() => openEvent(e)} className={`w-full text-left truncate text-[11px] px-1.5 py-1 rounded border ${k.chip} hover:brightness-95`}>
                        {e.time ? <b>{e.time} </b> : null}{e.title}{isManager && e.assignee ? ` · ${e.assignee.split(" ")[0]}` : ""}
                      </button>
                    );
                  })}
                  {list.length > 3 && <p className="text-[10px] text-slate-400 pl-1">+{list.length - 3} more</p>}
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      <LeadDrawer leadId={selected} open={open} onOpenChange={setOpen} onChange={load} members={members} />
    </div>
  );
}
