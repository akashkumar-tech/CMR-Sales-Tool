import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useAutoRefresh } from "@/lib/useAutoRefresh";
import { fmtDate } from "@/lib/crm";
import { toast } from "sonner";
import LeadDrawer from "@/components/LeadDrawer";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ChevronLeft, ChevronRight } from "lucide-react";

const KIND = {
  demo: { label: "Demo", chip: "bg-purple-100 text-purple-700 border-purple-200", dot: "bg-purple-500" },
  followup: { label: "Follow-up", chip: "bg-amber-100 text-amber-800 border-amber-200", dot: "bg-amber-500" },
  task: { label: "Task", chip: "bg-primary/10 text-primary border-primary/20", dot: "bg-primary" },
};
const TASK_STATUSES = ["To Do", "In Progress", "Completed", "Cancelled"];
// Local calendar date (toISOString() would convert local midnight to UTC and shift every cell by a day east of UTC).
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const SHOWN_PER_DAY = 3;

export default function CalendarPage() {
  const { user, isManager } = useAuth();
  const [cursor, setCursor] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); });
  const [events, setEvents] = useState([]);
  const [loadError, setLoadError] = useState(false);
  const [members, setMembers] = useState([]);
  const [employee, setEmployee] = useState("all");
  const [selected, setSelected] = useState(null);
  const [open, setOpen] = useState(false);
  const [dayOpen, setDayOpen] = useState(null);   // "YYYY-MM-DD" whose full list is shown
  const [task, setTask] = useState(null);         // task event shown in the detail dialog
  const reqSeq = useRef(0);

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
    // Only the latest request may update the grid: a slow reply for a previous month/filter is ignored.
    const seq = ++reqSeq.current;
    api.get(`/calendar?${p.toString()}`)
      .then((r) => { if (seq === reqSeq.current) { setEvents(r.data.events); setLoadError(false); } })
      .catch(() => { if (seq === reqSeq.current) setLoadError(true); });
  }, [grid, employee, isManager]);
  useEffect(() => { load(); }, [load]);
  useAutoRefresh(load, 12000);
  // Everyone needs the team directory (lead drawer assignee lists); managers also use it for the filter.
  useEffect(() => { api.get("/users").then((r) => setMembers(r.data)).catch(() => {}); }, []);

  const byDay = useMemo(() => {
    const m = {};
    events.forEach((e) => { (m[e.date] = m[e.date] || []).push(e); });
    Object.values(m).forEach((list) => list.sort((a, b) => (a.time || "99").localeCompare(b.time || "99")));
    return m;
  }, [events]);

  const todayISO = iso(new Date());
  const openEvent = (e) => {
    setDayOpen(null);
    if (e.kind === "task") { setTask(e); return; }
    if (e.lead_id) { setSelected(e.lead_id); setOpen(true); }
  };
  const openLead = (id) => { setTask(null); setSelected(id); setOpen(true); };
  const shift = (n) => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + n, 1));

  const chip = (e, full, key) => {
    const k = KIND[e.kind];
    const extra = e.done && e.kind !== "task" && e.status && e.status !== "Scheduled" ? ` · ${e.status}` : "";
    return (
      <button key={key} data-testid={`cal-event-${e.kind}-${e.task_id || e.lead_id}`} data-done={e.done ? "true" : "false"} onClick={() => openEvent(e)}
        title={e.done ? `${k.label} — ${e.status}` : k.label}
        className={`w-full text-left ${full ? "text-xs px-2 py-1.5" : "truncate text-[11px] px-1.5 py-1"} rounded border ${k.chip} hover:brightness-95 ${e.done ? "opacity-50 line-through" : ""}`}>
        {e.time ? <b>{e.time} </b> : null}{e.title}{extra}{isManager && e.assignee ? ` · ${e.assignee.split(" ")[0]}` : ""}
      </button>
    );
  };

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-primary">Schedule</p>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-900">Calendar</h1>
          <p className="text-sm text-slate-500 mt-1">{isManager ? "Your team's demos, follow-ups and tasks." : "Your demos, follow-ups and tasks."} Click a demo or follow-up to open the lead, or a task to see and update it.</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {isManager && members.length > 0 && (
            <select data-testid="calendar-employee-select" value={employee} onChange={(e) => setEmployee(e.target.value)} className="h-9 rounded-lg border border-border text-sm px-2 text-slate-600">
              <option value="all">Whole team</option>
              {members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
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

      <div className="flex items-center gap-4 text-xs text-slate-500 flex-wrap">
        {Object.entries(KIND).map(([k, v]) => <span key={k} className="inline-flex items-center gap-1.5"><span className={`h-2.5 w-2.5 rounded-full ${v.dot}`} /> {v.label}</span>)}
        <span className="inline-flex items-center gap-1.5"><span className="line-through opacity-50">Done</span> = completed / no-show</span>
      </div>

      {loadError && (
        <div data-testid="calendar-load-error" className="text-sm bg-rose-50 border border-rose-200 text-rose-700 rounded-lg px-3 py-2 flex items-center justify-between">
          <span>Couldn't load the latest calendar — showing what was loaded before.</span>
          <button onClick={load} className="font-semibold hover:underline">Try again</button>
        </div>
      )}

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
                  {list.slice(0, SHOWN_PER_DAY).map((e, j) => chip(e, false, j))}
                  {list.length > SHOWN_PER_DAY && (
                    <button data-testid={`cal-more-${key}`} onClick={() => setDayOpen(key)} className="text-[10px] font-semibold text-primary hover:underline pl-1">
                      +{list.length - SHOWN_PER_DAY} more
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      <Dialog open={!!dayOpen} onOpenChange={(v) => !v && setDayOpen(null)}>
        <DialogContent className="bg-white max-h-[85vh] overflow-y-auto" data-testid="calendar-day-dialog">
          <DialogHeader><DialogTitle>{dayOpen ? fmtDate(dayOpen) : ""}</DialogTitle></DialogHeader>
          <div className="space-y-1.5">{(byDay[dayOpen] || []).map((e, j) => chip(e, true, j))}</div>
        </DialogContent>
      </Dialog>

      <TaskDialog task={task} onClose={() => setTask(null)} onOpenLead={openLead} onChanged={() => { setTask(null); load(); }}
        canEdit={!!task && (isManager || task.assignee_id === user?.id)} />

      <LeadDrawer leadId={selected} open={open} onOpenChange={setOpen} onChange={load} members={members} />
    </div>
  );
}

function TaskDialog({ task, onClose, onOpenLead, onChanged, canEdit }) {
  const [form, setForm] = useState({ due_date: "", due_time: "", status: "To Do" });
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (task) setForm({ due_date: task.date || "", due_time: task.time || "", status: TASK_STATUSES.includes(task.status) ? task.status : "To Do" });
  }, [task]);
  if (!task) return null;

  const save = async () => {
    const changes = {};
    if (form.due_date && form.due_date !== task.date) changes.due_date = form.due_date;
    if ((form.due_time || "") !== (task.time || "")) changes.due_time = form.due_time;
    if (form.status !== task.status) changes.status = form.status;
    if (!Object.keys(changes).length) return onClose();
    setBusy(true);
    try { await api.patch(`/tasks/${task.task_id}`, changes); toast.success("Task updated"); onChanged(); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!window.confirm(`Delete the task "${task.title}"?`)) return;
    setBusy(true);
    try { await api.delete(`/tasks/${task.task_id}`); toast.success("Task deleted"); onChanged(); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="bg-white" data-testid="calendar-task-dialog">
        <DialogHeader><DialogTitle>{task.title}</DialogTitle></DialogHeader>
        <div className="space-y-3 text-sm">
          <p className="text-slate-600">
            For <b>{task.assignee}</b>{task.assigned_by_name ? <> · assigned by {task.assigned_by_name}</> : null}
            {task.priority ? <> · {task.priority} priority</> : null}
            {task.lead_name ? <> · lead <b>{task.lead_name}</b></> : null}
          </p>
          {task.notes && <p className="text-slate-500 whitespace-pre-wrap">{task.notes}</p>}
          <div className="grid grid-cols-3 gap-3">
            <div><Label>Due date</Label><Input type="date" data-testid="task-dialog-date" value={form.due_date} disabled={!canEdit} onChange={(e) => setForm((f) => ({ ...f, due_date: e.target.value }))} /></div>
            <div><Label>Due time</Label><Input type="time" data-testid="task-dialog-time" value={form.due_time} disabled={!canEdit} onChange={(e) => setForm((f) => ({ ...f, due_time: e.target.value }))} /></div>
            <div><Label>Status</Label>
              <Select value={form.status} onValueChange={(v) => setForm((f) => ({ ...f, status: v }))} disabled={!canEdit}>
                <SelectTrigger data-testid="task-dialog-status"><SelectValue /></SelectTrigger>
                <SelectContent>{TASK_STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
        </div>
        <DialogFooter className="gap-2 sm:justify-between">
          <div className="flex gap-2">
            {canEdit && <Button variant="outline" className="text-destructive" data-testid="task-dialog-delete" disabled={busy} onClick={remove}>Delete</Button>}
            {task.lead_id && <Button variant="outline" data-testid="task-dialog-open-lead" onClick={() => onOpenLead(task.lead_id)}>Open lead</Button>}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose}>Close</Button>
            {canEdit && <Button data-testid="task-dialog-save" disabled={busy} onClick={save}>{busy ? "Saving…" : "Save"}</Button>}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
