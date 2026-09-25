import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { initials } from "@/lib/crm";
import { useAutoRefresh } from "@/lib/useAutoRefresh";
import { Card } from "@/components/ui/card";

const METRICS = [
  ["open_leads", "Open Leads", "text-slate-900"],
  ["open_tasks", "Open Tasks", "text-slate-900"],
  ["today_tasks", "Due Today", "text-sky-700"],
  ["overdue_tasks", "Overdue Tasks", "text-rose-600"],
  ["upcoming_demos", "Upcoming Demos", "text-purple-700"],
  ["open_follow_ups", "Open Follow-ups", "text-amber-700"],
  ["overdue_follow_ups", "Overdue Follow-ups", "text-rose-600"],
];

export default function Workload() {
  const navigate = useNavigate();
  const [rows, setRows] = useState([]);
  const [teams, setTeams] = useState([]);
  const [team, setTeam] = useState("all");

  const load = useCallback(() => {
    const p = new URLSearchParams(); if (team !== "all") p.set("team", team);
    api.get(`/workload?${p.toString()}`).then((r) => setRows(r.data.rows)).catch(() => {});
  }, [team]);
  useEffect(() => { load(); }, [load]);
  useAutoRefresh(load, 10000);
  useEffect(() => { api.get("/teams").then((r) => setTeams(r.data)).catch(() => {}); }, []);

  const goLeads = (uid, extra = "") => () => navigate(`/all-leads?owner=${uid}${extra}`);

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-primary">Manager View</p>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-900">Team Workload</h1>
          <p className="text-sm text-slate-500 mt-1">Live view of what each person is carrying — balance the load, spot the overloaded.</p>
        </div>
        {teams.length > 0 && (
          <select data-testid="workload-team-select" value={team} onChange={(e) => setTeam(e.target.value)} className="h-9 rounded-lg border border-border text-sm px-2 text-slate-600">
            <option value="all">All Teams</option>
            {teams.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        )}
      </div>

      <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
        {rows.map((r) => {
          const load = r.open_leads + r.open_tasks;
          const busy = r.overdue_tasks + r.overdue_follow_ups;
          return (
            <Card key={r.employee_id} data-testid={`workload-card-${r.employee_id}`} className="p-5">
              <div className="flex items-center gap-3 mb-4">
                <div className="h-10 w-10 rounded-full bg-primary/10 text-primary grid place-items-center font-bold">{initials(r.name)}</div>
                <div className="flex-1"><p className="font-bold text-slate-900">{r.name}</p><p className="text-xs text-slate-500 capitalize">{r.role}{r.team ? ` · ${r.team}` : ""}</p></div>
                {busy > 0 ? <span className="text-[11px] px-2 py-0.5 rounded-full bg-rose-100 text-rose-700 font-semibold">{busy} overdue</span> : <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 font-semibold">on track</span>}
              </div>
              <div className="grid grid-cols-2 gap-2">
                <button onClick={goLeads(r.employee_id)} className="text-left p-2.5 rounded-lg bg-slate-50 hover:bg-slate-100 transition-colors">
                  <p className="text-xl font-extrabold text-slate-900">{r.open_leads}</p><p className="text-[11px] text-slate-500">Open Leads</p>
                </button>
                <div className="text-left p-2.5 rounded-lg bg-slate-50">
                  <p className="text-xl font-extrabold text-slate-900">{r.open_tasks}</p><p className="text-[11px] text-slate-500">Open Tasks</p>
                </div>
                <div className="text-left p-2.5 rounded-lg bg-slate-50">
                  <p className="text-xl font-extrabold text-purple-700">{r.upcoming_demos}</p><p className="text-[11px] text-slate-500">Upcoming Demos</p>
                </div>
                <button onClick={goLeads(r.employee_id, "&follow_up=overdue")} className="text-left p-2.5 rounded-lg bg-slate-50 hover:bg-slate-100 transition-colors">
                  <p className={`text-xl font-extrabold ${r.overdue_follow_ups > 0 ? "text-rose-600" : "text-slate-900"}`}>{r.overdue_follow_ups}</p><p className="text-[11px] text-slate-500">Overdue Follow-ups</p>
                </button>
              </div>
              <div className="flex justify-between mt-3 pt-3 border-t border-border text-xs text-slate-500">
                <span>Due today: <b className="text-sky-700">{r.today_tasks}</b></span>
                <span>Overdue tasks: <b className={r.overdue_tasks > 0 ? "text-rose-600" : "text-slate-700"}>{r.overdue_tasks}</b></span>
                <span>Follow-ups: <b className="text-amber-700">{r.open_follow_ups}</b></span>
              </div>
            </Card>
          );
        })}
        {rows.length === 0 && <p className="text-sm text-slate-400 col-span-full text-center py-10">No active team members.</p>}
      </div>
    </div>
  );
}
