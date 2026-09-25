import { useCallback, useEffect, useRef, useState } from "react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { fmtDate } from "@/lib/crm";
import { useAutoRefresh } from "@/lib/useAutoRefresh";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Plus, User } from "lucide-react";

const VIEWS = [["mine", "My Tasks"], ["today", "Due Today"], ["overdue", "Overdue"], ["upcoming", "Upcoming"], ["completed", "Completed"]];
const STATUSES = ["To Do", "In Progress", "Completed", "Cancelled"];
const PRIORITIES = ["Low", "Medium", "High", "Urgent"];

const priorityStyle = (p) => ({
  Urgent: "bg-red-600 text-white", High: "bg-rose-100 text-rose-700",
  Medium: "bg-amber-100 text-amber-700", Low: "bg-slate-100 text-slate-600",
}[p] || "bg-amber-100 text-amber-700");

const statusStyle = (s) => ({
  "To Do": "bg-slate-100 text-slate-600", "In Progress": "bg-sky-100 text-sky-700",
  "Completed": "bg-emerald-100 text-emerald-700", "Overdue": "bg-red-100 text-red-700",
  "Cancelled": "bg-zinc-200 text-zinc-500",
}[s] || "bg-slate-100 text-slate-600");

export default function Tasks() {
  const { isManager } = useAuth();
  const [view, setView] = useState("mine");
  const [tasks, setTasks] = useState([]);
  const [members, setMembers] = useState([]);
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const creatingRef = useRef(false);
  const [form, setForm] = useState({ title: "", due_date: "", due_time: "", priority: "Medium", notes: "", assigned_to: "" });

  const load = useCallback(() => {
    api.get(`/tasks?view=${view}`).then((r) => setTasks(r.data)).catch(() => {});
  }, [view]);
  useEffect(() => { load(); }, [load]);
  useAutoRefresh(load, 8000);
  useEffect(() => { if (isManager) api.get("/users").then((r) => setMembers(r.data.filter((u) => ["employee", "manager", "intern"].includes(u.role)))).catch(() => {}); }, [isManager]);

  const memberName = (id) => members.find((m) => m.id === id)?.name;
  const setStatus = async (t, status) => {
    try { await api.patch(`/tasks/${t.id}`, { status }); load(); }
    catch (e) { toast.error(apiError(e)); }
  };

  const create = async () => {
    if (!form.title) return toast.error("Task title required");
    if (creatingRef.current) return;   // a double-click fires twice before React re-renders
    creatingRef.current = true; setCreating(true);
    try {
      const p = { ...form }; if (!isManager) delete p.assigned_to;
      await api.post("/tasks", p);
      toast.success(p.assigned_to ? "Task created & assignee notified" : "Task created");
      setOpen(false); setForm({ title: "", due_date: "", due_time: "", priority: "Medium", notes: "", assigned_to: "" }); load();
    } catch (e) { toast.error(apiError(e)); } finally { creatingRef.current = false; setCreating(false); }
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div><p className="text-[11px] font-bold uppercase tracking-[0.16em] text-primary">Task Manager</p><h1 className="text-3xl font-extrabold tracking-tight text-slate-900">Tasks</h1></div>
        <Button data-testid="add-task-btn" onClick={() => setOpen(true)} className="gap-2"><Plus size={16} /> New Task</Button>
      </div>
      <Tabs value={view} onValueChange={setView}>
        <TabsList>{VIEWS.map(([v, l]) => <TabsTrigger key={v} value={v} data-testid={`task-view-${v}`}>{l}</TabsTrigger>)}</TabsList>
      </Tabs>
      <Card className="divide-y divide-border">
        {tasks.map((t) => (
          <div key={t.id} data-testid={`task-row-${t.id}`} className="flex items-center gap-4 p-4">
            <div className="flex-1 min-w-0">
              <p className={`text-sm font-semibold ${t.status === "Completed" ? "line-through text-slate-400" : "text-slate-900"}`}>{t.title}</p>
              <p className="text-xs text-slate-500 truncate">
                {t.lead_name || "No lead"} · due {fmtDate(t.due_date)}{t.due_time ? ` ${t.due_time}` : ""}
                {t.assigned_by_name && <span className="inline-flex items-center gap-1 ml-1"><User size={11} /> by {t.assigned_by_name}</span>}
                {isManager && t.assigned_to && memberName(t.assigned_to) && <span> · to {memberName(t.assigned_to)}</span>}
              </p>
              {t.notes && <p className="text-xs text-slate-400 mt-0.5 truncate">{t.notes}</p>}
            </div>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${priorityStyle(t.priority)}`}>{t.priority}</span>
            <Select value={STATUSES.includes(t.status) ? t.status : "To Do"} onValueChange={(v) => setStatus(t, v)}>
              <SelectTrigger data-testid={`task-status-${t.id}`} className={`w-36 h-8 text-xs font-medium border-0 ${statusStyle(t.status)}`}><SelectValue /></SelectTrigger>
              <SelectContent>{STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
            </Select>
          </div>
        ))}
        {tasks.length === 0 && <div className="p-10 text-center text-slate-400 text-sm">No tasks here.</div>}
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-white">
          <DialogHeader><DialogTitle>New Task</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Task</Label><Input data-testid="task-title-input" value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} /></div>
            <div className="grid grid-cols-3 gap-3">
              <div><Label>Due Date</Label><Input type="date" value={form.due_date} onChange={(e) => setForm((f) => ({ ...f, due_date: e.target.value }))} /></div>
              <div><Label>Due Time</Label><Input type="time" value={form.due_time} onChange={(e) => setForm((f) => ({ ...f, due_time: e.target.value }))} /></div>
              <div><Label>Priority</Label>
                <Select value={form.priority} onValueChange={(v) => setForm((f) => ({ ...f, priority: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{PRIORITIES.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            {isManager && (
              <div><Label>Assign To</Label>
                <Select value={form.assigned_to} onValueChange={(v) => setForm((f) => ({ ...f, assigned_to: v }))}>
                  <SelectTrigger data-testid="task-assignee-select"><SelectValue placeholder="Default: you" /></SelectTrigger>
                  <SelectContent>{members.map((m) => <SelectItem key={m.id} value={m.id}>{m.name} · {m.role}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            )}
            <div><Label>Notes / instructions</Label><Textarea value={form.notes} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} /></div>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button><Button data-testid="save-task-btn" onClick={create} disabled={creating}>{creating ? "Creating…" : "Create"}</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
