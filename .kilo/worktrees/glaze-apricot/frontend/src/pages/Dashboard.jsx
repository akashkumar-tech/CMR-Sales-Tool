import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { stageStyle, fmtDate, fmtDateTime } from "@/lib/crm";
import { useAutoRefresh } from "@/lib/useAutoRefresh";
import { Card } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import {
  Users, Phone, CheckSquare, TrendingUp, AlertCircle, Calendar, MessageSquare,
  Star, CheckCircle2, Reply, Lock, Activity as ActivityIcon,
} from "lucide-react";

const Stat = ({ icon: Icon, label, value, tone = "text-primary bg-primary/10", testid, onClick }) => (
  <Card data-testid={testid} onClick={onClick} className={`p-4 flex items-center gap-3 transition-transform ${onClick ? "cursor-pointer hover:-translate-y-0.5 hover:shadow-md" : ""}`}>
    <div className={`h-10 w-10 rounded-xl grid place-items-center shrink-0 ${tone}`}><Icon size={18} /></div>
    <div className="min-w-0"><p className="text-xl font-extrabold text-slate-900">{value ?? 0}</p><p className="text-[11px] font-medium text-slate-500 leading-tight">{label}</p></div>
  </Card>
);

export default function Dashboard() {
  const { user, isManager } = useAuth();
  return isManager ? <ManagerDashboard user={user} /> : <EmployeeDashboard user={user} />;
}

/* ---------------- Manager / Admin: operational command centre ---------------- */
function ManagerDashboard({ user }) {
  const navigate = useNavigate();
  const [perf, setPerf] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [leads, setLeads] = useState([]);

  const load = () => {
    api.get("/performance/team?period=month").then((r) => setPerf(aggregate(r.data.rows))).catch(() => {});
    api.get("/tasks?view=today").then((r) => setTasks(r.data)).catch(() => {});
    api.get("/leads?scope=mine").then((r) => setLeads(r.data.slice(0, 6))).catch(() => {});
  };
  useEffect(() => { load(); }, []);
  useAutoRefresh(load, 10000);

  function aggregate(rows) {
    const sum = (k) => rows.reduce((a, r) => a + (r[k] || 0), 0);
    return { leads_added: sum("leads_added"), calls: sum("calls"), messages: sum("messages"), interested: sum("interested"),
      conversions: sum("conversions"), demos_booked: sum("demos_booked"), lost: sum("lost"), overdue_follow_ups: sum("overdue_follow_ups") };
  }
  const go = (qs) => () => navigate(`/all-leads?${qs}`);

  return (
    <div className="space-y-6">
      <div>
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-primary">Manager Command Centre</p>
        <h1 className="text-3xl font-extrabold tracking-tight text-slate-900">Welcome back, {user?.name}</h1>
        <p className="text-sm text-slate-500 mt-1">Your team's activity this month. Tap any metric to open the leads behind it.</p>
      </div>
      {perf && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <Stat testid="stat-leads" icon={Users} label="Team Leads Added" value={perf.leads_added} onClick={go("")} />
          <Stat testid="stat-interested" icon={Star} label="Interested" value={perf.interested} tone="text-amber-600 bg-amber-50" onClick={go("status=Interested")} />
          <Stat testid="stat-demos" icon={Calendar} label="Demos Booked" value={perf.demos_booked} tone="text-purple-600 bg-purple-50" onClick={go("status=Demo Booked")} />
          <Stat testid="stat-conversions" icon={TrendingUp} label="Conversions" value={perf.conversions} tone="text-teal-600 bg-teal-50" onClick={go("status=Converted")} />
          <Stat testid="stat-calls" icon={Phone} label="Calls Made" value={perf.calls} tone="text-emerald-600 bg-emerald-50" />
          <Stat testid="stat-messages" icon={MessageSquare} label="Messages Sent" value={perf.messages} tone="text-blue-600 bg-blue-50" />
          <Stat testid="stat-lost" icon={AlertCircle} label="Lost / Not Interested" value={perf.lost} tone="text-rose-600 bg-rose-50" onClick={go("status=Lost")} />
          <Stat testid="stat-overdue" icon={AlertCircle} label="Overdue Follow-ups" value={perf.overdue_follow_ups} tone="text-rose-600 bg-rose-50" onClick={go("follow_up=overdue")} />
        </div>
      )}
      <div className="grid lg:grid-cols-2 gap-6">
        <TaskList title="Today's Tasks & Follow-ups" tasks={tasks} />
        <RecentLeads leads={leads} />
      </div>
    </div>
  );
}

/* ---------------- Employee / Intern: action-focused personal workspace ---------------- */
function EmployeeDashboard({ user }) {
  const navigate = useNavigate();
  const [perf, setPerf] = useState(null);
  const [taskView, setTaskView] = useState("today");
  const [tasks, setTasks] = useState([]);
  const [leads, setLeads] = useState([]);
  const [acts, setActs] = useState([]);

  const loadPerf = () => api.get("/performance/me?period=month").then((r) => setPerf(r.data)).catch(() => {});
  const loadTasks = () => api.get(`/tasks?view=${taskView}`).then((r) => setTasks(r.data)).catch(() => {});
  const loadLeads = () => api.get("/leads?scope=mine").then((r) => setLeads(r.data)).catch(() => {});
  const loadActs = () => api.get("/activities").then((r) => setActs(r.data.slice(0, 8))).catch(() => {});

  useEffect(() => { loadPerf(); loadLeads(); loadActs(); }, []);
  useEffect(() => { loadTasks(); }, [taskView]);
  useAutoRefresh(() => { loadPerf(); loadTasks(); loadLeads(); loadActs(); }, 8000);

  const openTerminal = ["Converted", "Lost", "Closed", "Not Interested"];
  const followUps = leads
    .filter((l) => l.next_follow_up && l.followup_assigned_to === user.id && !openTerminal.includes(l.status))
    .sort((a, b) => (a.next_follow_up || "").localeCompare(b.next_follow_up || "")).slice(0, 6);
  const demos = leads
    .filter((l) => l.demo_owner === user.id && l.demo_date)
    .sort((a, b) => (a.demo_date || "").localeCompare(b.demo_date || "")).slice(0, 6);

  const completeTask = async (t) => { try { await api.patch(`/tasks/${t.id}`, { status: "Completed" }); loadTasks(); loadPerf(); } catch {} };
  const go = (qs) => () => navigate(`/my-leads?${qs}`);

  return (
    <div className="space-y-6" data-testid="employee-dashboard">
      <div>
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-primary">My Workspace</p>
        <h1 className="text-3xl font-extrabold tracking-tight text-slate-900">Welcome back, {user?.name}</h1>
        <p className="text-sm text-slate-500 mt-1 inline-flex items-center gap-1.5"><Lock size={13} /> Your personal leads, tasks and performance this month. Only you can see these numbers.</p>
      </div>

      {perf && (
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3" data-testid="my-kpis">
          <Stat testid="kpi-leads-added" icon={Users} label="Leads Added" value={perf.leads_added} onClick={go("")} />
          <Stat testid="kpi-contacted" icon={Phone} label="Contacted" value={perf.contacted} tone="text-emerald-600 bg-emerald-50" />
          <Stat testid="kpi-responses" icon={Reply} label="Responses" value={perf.responses} tone="text-blue-600 bg-blue-50" />
          <Stat testid="kpi-interested" icon={Star} label="Interested" value={perf.interested} tone="text-amber-600 bg-amber-50" onClick={go("status=Interested")} />
          <Stat testid="kpi-demos-booked" icon={Calendar} label="Demos Booked" value={perf.demos_booked} tone="text-purple-600 bg-purple-50" onClick={go("status=Demo Booked")} />
          <Stat testid="kpi-demos-done" icon={CheckCircle2} label="Demos Completed" value={perf.demos_completed} tone="text-purple-600 bg-purple-50" onClick={go("status=Demo Completed")} />
          <Stat testid="kpi-followups" icon={CheckSquare} label="Follow-ups Done" value={perf.follow_ups} tone="text-teal-600 bg-teal-50" />
          <Stat testid="kpi-conversions" icon={TrendingUp} label="Conversions" value={perf.conversions} tone="text-teal-600 bg-teal-50" onClick={go("status=Converted")} />
          <Stat testid="kpi-tasks-done" icon={CheckCircle2} label="Tasks Completed" value={perf.tasks_completed} tone="text-emerald-600 bg-emerald-50" />
          <Stat testid="kpi-overdue" icon={AlertCircle} label="Overdue Follow-ups" value={perf.overdue_follow_ups} tone="text-rose-600 bg-rose-50" onClick={go("follow_up=overdue")} />
        </div>
      )}

      <div className="grid lg:grid-cols-2 gap-6">
        <Card className="p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-bold text-slate-900">My Tasks</h3>
            <Tabs value={taskView} onValueChange={setTaskView}>
              <TabsList className="h-8">
                <TabsTrigger value="today" data-testid="my-task-today" className="text-xs px-2 h-6">Today</TabsTrigger>
                <TabsTrigger value="overdue" data-testid="my-task-overdue" className="text-xs px-2 h-6">Overdue</TabsTrigger>
                <TabsTrigger value="upcoming" data-testid="my-task-upcoming" className="text-xs px-2 h-6">Upcoming</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>
          {tasks.length === 0 && <p className="text-sm text-slate-400">Nothing here. 🎯</p>}
          <div className="space-y-2">
            {tasks.map((t) => (
              <div key={t.id} data-testid={`my-task-${t.id}`} className="flex items-center gap-3 p-2.5 rounded-lg bg-slate-50">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-800 truncate">{t.title}</p>
                  <p className="text-xs text-slate-500 truncate">{t.lead_name} · due {fmtDate(t.due_date)}{t.due_time ? ` ${t.due_time}` : ""}{t.assigned_by_name && t.assigned_by !== user.id ? ` · by ${t.assigned_by_name}` : ""}</p>
                </div>
                <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${t.priority === "Urgent" ? "bg-red-600 text-white" : t.priority === "High" ? "bg-rose-100 text-rose-700" : "bg-slate-200 text-slate-600"}`}>{t.priority}</span>
                <Button size="sm" variant="outline" className="h-7 text-xs" data-testid={`complete-task-${t.id}`} onClick={() => completeTask(t)}>Done</Button>
              </div>
            ))}
          </div>
        </Card>

        <Card className="p-5">
          <div className="flex items-center justify-between mb-3"><h3 className="font-bold text-slate-900">My Follow-ups</h3><button onClick={() => navigate("/my-leads?follow_up=today")} className="text-xs text-primary hover:underline">View all</button></div>
          {followUps.length === 0 && <p className="text-sm text-slate-400">No follow-ups assigned to you.</p>}
          <div className="space-y-2">
            {followUps.map((l) => (
              <div key={l.id} data-testid={`my-followup-${l.id}`} className="flex items-center justify-between p-2.5 rounded-lg bg-slate-50">
                <div className="min-w-0"><p className="text-sm font-medium text-slate-800 truncate">{l.name}</p><p className="text-xs text-slate-500">follow-up {fmtDate(l.next_follow_up)}</p></div>
                <span className={`text-xs px-2 py-0.5 rounded-full border ${stageStyle(l.status)}`}>{l.status}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card className="p-5">
          <div className="flex items-center justify-between mb-3"><h3 className="font-bold text-slate-900">My Demos</h3><button onClick={() => navigate("/demos")} className="text-xs text-primary hover:underline">Open demos</button></div>
          {demos.length === 0 && <p className="text-sm text-slate-400">No demos assigned to you.</p>}
          <div className="space-y-2">
            {demos.map((l) => (
              <div key={l.id} data-testid={`my-demo-${l.id}`} className="flex items-center justify-between p-2.5 rounded-lg bg-slate-50">
                <div className="min-w-0"><p className="text-sm font-medium text-slate-800 truncate">{l.name}</p><p className="text-xs text-slate-500">{fmtDate(l.demo_date)}{l.demo_time ? ` · ${l.demo_time}` : ""}</p></div>
                <span className="text-xs px-2 py-0.5 rounded-full bg-purple-50 text-purple-700 border border-purple-100">{l.demo_status || "Scheduled"}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card className="p-5">
          <h3 className="font-bold text-slate-900 mb-3">My Recent Activity</h3>
          {acts.length === 0 && <p className="text-sm text-slate-400">No activity logged yet.</p>}
          <div className="space-y-2.5">
            {acts.map((a) => (
              <div key={a.id} className="flex gap-2.5" data-testid={`my-activity-${a.id}`}>
                <div className="h-7 w-7 rounded-full bg-primary/10 text-primary grid place-items-center shrink-0"><ActivityIcon size={13} /></div>
                <div className="min-w-0 border-b border-border pb-2 flex-1"><p className="text-sm text-slate-800 truncate"><b>{a.type}</b> · {a.lead_name}</p><p className="text-[11px] text-slate-400">{fmtDateTime(a.timestamp)}</p></div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

function TaskList({ title, tasks }) {
  return (
    <Card className="p-5">
      <h3 className="font-bold text-slate-900 mb-3">{title}</h3>
      {tasks.length === 0 && <p className="text-sm text-slate-400">Nothing due today. 🎯</p>}
      <div className="space-y-2">
        {tasks.map((t) => (
          <div key={t.id} className="flex items-center justify-between p-2.5 rounded-lg bg-slate-50">
            <div><p className="text-sm font-medium text-slate-800">{t.title}</p><p className="text-xs text-slate-500">{t.lead_name}</p></div>
            <span className={`text-xs px-2 py-0.5 rounded-full ${t.priority === "High" || t.priority === "Urgent" ? "bg-rose-100 text-rose-700" : "bg-slate-200 text-slate-600"}`}>{t.priority}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}

function RecentLeads({ leads }) {
  return (
    <Card className="p-5">
      <h3 className="font-bold text-slate-900 mb-3">My Recent Leads</h3>
      <div className="space-y-2">
        {leads.map((l) => (
          <div key={l.id} className="flex items-center justify-between p-2.5 rounded-lg bg-slate-50">
            <div><p className="text-sm font-medium text-slate-800">{l.name}</p><p className="text-xs text-slate-500">{l.practice} · follow-up {fmtDate(l.next_follow_up)}</p></div>
            <span className={`text-xs px-2 py-0.5 rounded-full border ${stageStyle(l.status)}`}>{l.status}</span>
          </div>
        ))}
        {leads.length === 0 && <p className="text-sm text-slate-400">No leads yet.</p>}
      </div>
    </Card>
  );
}
