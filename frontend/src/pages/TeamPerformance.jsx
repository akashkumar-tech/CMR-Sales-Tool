import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { initials } from "@/lib/crm";
import { Card } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

const PERIODS = [["today", "Today"], ["week", "This Week"], ["month", "This Month"], ["custom", "Custom"]];
const COLS = [
  ["leads_added", "Leads"], ["contacted", "Contacted"], ["calls", "Calls"], ["messages", "Messages"],
  ["responses", "Responses"], ["interested", "Interested"], ["demos_booked", "Demos Booked"],
  ["demos_completed", "Demos Done"], ["demo_noshows", "No-shows"], ["trials", "Trials"],
  ["pricing_shared", "Pricing"], ["invoices", "Invoices"], ["payment_pending", "Pay Pending"],
  ["paid", "Paid"], ["conversions", "Conversions"], ["lost", "Lost"], ["closed", "Closed"],
  ["tasks_completed", "Tasks"], ["overdue_follow_ups", "Overdue"],
];

export default function TeamPerformance() {
  const [period, setPeriod] = useState("month");
  const [rows, setRows] = useState([]);
  const [members, setMembers] = useState([]);
  const [teams, setTeams] = useState([]);
  const [team, setTeam] = useState("all");
  const [employee, setEmployee] = useState("all");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");

  const load = useCallback(() => {
    const p = new URLSearchParams({ period });
    if (period === "custom" && start && end) { p.set("start", start); p.set("end", end); }
    if (employee !== "all") p.set("employee", employee);
    if (team !== "all") p.set("team", team);
    api.get(`/performance/team?${p.toString()}`).then((r) => setRows(r.data.rows));
  }, [period, employee, team, start, end]);

  useEffect(() => { api.get("/users").then((r) => setMembers(r.data.filter((u) => u.role !== "admin"))); api.get("/teams").then((r) => setTeams(r.data)).catch(() => {}); }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-5">
      <div><p className="text-[11px] font-bold uppercase tracking-[0.16em] text-primary">Manager View</p><h1 className="text-3xl font-extrabold tracking-tight text-slate-900">Team Performance</h1><p className="text-sm text-slate-500 mt-1">Collaborative operational overview — no automatic ranking or scoring.</p></div>

      <Card className="p-3 flex flex-wrap items-center gap-3">
        <Tabs value={period} onValueChange={setPeriod}><TabsList>{PERIODS.map(([v, l]) => <TabsTrigger key={v} value={v} data-testid={`perf-period-${v}`}>{l}</TabsTrigger>)}</TabsList></Tabs>
        {period === "custom" && (
          <div className="flex items-center gap-2">
            <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="w-40" data-testid="perf-start" />
            <span className="text-slate-400">to</span>
            <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="w-40" data-testid="perf-end" />
            <Button size="sm" onClick={load}>Apply</Button>
          </div>
        )}
        <div className="flex gap-2 ml-auto flex-wrap items-center">
          {teams.length > 0 && (
            <select data-testid="perf-team-select" value={team} onChange={(e) => setTeam(e.target.value)} className="h-8 rounded-lg border border-border text-xs px-2 text-slate-600">
              <option value="all">All Teams</option>
              {teams.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          )}
          <button onClick={() => setEmployee("all")} className={`px-3 py-1.5 rounded-full text-xs font-medium border ${employee === "all" ? "bg-primary text-white border-primary" : "border-border text-slate-600"}`}>All</button>
          {members.map((m) => <button key={m.id} data-testid={`perf-emp-${m.name.toLowerCase()}`} onClick={() => setEmployee(m.id)} className={`px-3 py-1.5 rounded-full text-xs font-medium border ${employee === m.id ? "bg-primary text-white border-primary" : "border-border text-slate-600"}`}>{m.name}</button>)}
        </div>
      </Card>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {rows.map((r) => (
          <Card key={r.employee_id} className="p-5">
            <div className="flex items-center gap-3 mb-3">
              <div className="h-10 w-10 rounded-full bg-primary/10 text-primary grid place-items-center font-bold">{initials(r.name)}</div>
              <div><p className="font-bold text-slate-900">{r.name}</p><p className="text-xs text-slate-500 capitalize">{r.role} · {r.conversions} conversions</p></div>
            </div>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div><p className="text-lg font-extrabold text-slate-900">{r.calls}</p><p className="text-[11px] text-slate-500">Calls</p></div>
              <div><p className="text-lg font-extrabold text-slate-900">{r.messages}</p><p className="text-[11px] text-slate-500">Messages</p></div>
              <div><p className="text-lg font-extrabold text-slate-900">{r.demos_completed}</p><p className="text-[11px] text-slate-500">Demos Done</p></div>
              <div><p className="text-lg font-extrabold text-rose-600">{r.overdue_follow_ups}</p><p className="text-[11px] text-slate-500">Overdue</p></div>
            </div>
          </Card>
        ))}
      </div>

      <Card className="overflow-hidden">
        <div className="overflow-x-auto scrollbar-thin">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-left"><tr><th className="px-4 py-3 font-semibold sticky left-0 bg-slate-50">Employee</th>{COLS.map(([k, l]) => <th key={k} className="px-3 py-3 font-semibold text-center whitespace-nowrap">{l}</th>)}</tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.employee_id} data-testid={`perf-row-${r.name.toLowerCase()}`} className="border-t border-border hover:bg-slate-50">
                  <td className="px-4 py-3 font-semibold text-slate-900 sticky left-0 bg-white">{r.name}</td>
                  {COLS.map(([k]) => <td key={k} className={`px-3 py-3 text-center ${k === "overdue_follow_ups" && r[k] > 0 ? "text-rose-600 font-bold" : "text-slate-700"}`}>{r[k]}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
