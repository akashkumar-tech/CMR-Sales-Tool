import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useAutoRefresh } from "@/lib/useAutoRefresh";
import { Card } from "@/components/ui/card";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line, CartesianGrid } from "recharts";

const COLORS = ["#E11D6B", "#0D9488", "#F59E0B", "#8B5CF6", "#0EA5E9", "#E11D48", "#10B981", "#6366F1"];
const PERIODS = [["day", "Day"], ["week", "Week"], ["month", "Month"], ["quarter", "Quarter"], ["year", "Year"], ["custom", "Custom"]];
const FUNNEL_COLORS = ["#6366F1", "#4F46E5", "#7C3AED", "#8B5CF6", "#A855F7", "#C026D3", "#D946EF", "#EC4899", "#F43F5E", "#10B981"];
// funnel stage -> lead status used for drill-down
const FUNNEL_STATUS = { "New Lead": "New Lead", Contacted: "Contacted", Interested: "Interested", Demo: "Demo Booked", Trial: "Trial", Pricing: "Pricing Shared", Invoice: "Invoice Raised", Payment: "Paid", Converted: "Converted" };

export default function Reports() {
  const { isManager } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [teams, setTeams] = useState([]);
  const [members, setMembers] = useState([]);
  const [team, setTeam] = useState("all");
  const [employee, setEmployee] = useState("all");
  const [period, setPeriod] = useState("month");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");

  useEffect(() => {
    if (isManager) {
      api.get("/teams").then((r) => setTeams(r.data)).catch(() => {});
      api.get("/users").then((r) => setMembers(r.data.filter((u) => u.role !== "admin"))).catch(() => {});
    }
  }, [isManager]);

  const load = useCallback(() => {
    const p = new URLSearchParams({ period });
    if (period === "custom") { if (!start || !end) return; p.set("start", start); p.set("end", end); }
    if (isManager && team !== "all") p.set("team", team);
    if (isManager && employee !== "all") p.set("employee", employee);
    api.get(`/reports?${p.toString()}`).then((r) => setData(r.data)).catch(() => {});
  }, [period, start, end, team, employee, isManager]);
  useEffect(() => { load(); }, [load]);
  useAutoRefresh(load, 12000);

  const leadBase = isManager ? "/all-leads" : "/my-leads";
  const goStatus = (status) => () => navigate(status ? `${leadBase}?status=${encodeURIComponent(status)}` : leadBase);

  const Stat = ({ label, value, tone, onClick, testid }) => (
    <Card data-testid={testid} onClick={onClick} className={`p-4 ${onClick ? "cursor-pointer hover:-translate-y-0.5 hover:shadow-md transition-transform" : ""}`}>
      <p className={`text-2xl font-extrabold ${tone}`}>{value}</p><p className="text-[11px] font-medium text-slate-500 mt-1">{label}</p>
    </Card>
  );

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div><p className="text-[11px] font-bold uppercase tracking-[0.16em] text-primary">Analytics</p><h1 className="text-3xl font-extrabold tracking-tight text-slate-900">Reports & Sales Funnel</h1></div>
        <div className="flex items-center gap-2 flex-wrap">
          <select data-testid="reports-period-select" value={period} onChange={(e) => setPeriod(e.target.value)} className="h-9 rounded-lg border border-border text-sm px-3 text-slate-600">
            {PERIODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          {period === "custom" && (
            <>
              <input type="date" data-testid="reports-start" value={start} onChange={(e) => setStart(e.target.value)} className="h-9 rounded-lg border border-border text-sm px-2 text-slate-600" />
              <input type="date" data-testid="reports-end" value={end} onChange={(e) => setEnd(e.target.value)} className="h-9 rounded-lg border border-border text-sm px-2 text-slate-600" />
            </>
          )}
          {isManager && teams.length > 0 && (
            <select data-testid="reports-team-select" value={team} onChange={(e) => setTeam(e.target.value)} className="h-9 rounded-lg border border-border text-sm px-3 text-slate-600">
              <option value="all">All Teams</option>{teams.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          )}
          {isManager && members.length > 0 && (
            <select data-testid="reports-employee-select" value={employee} onChange={(e) => setEmployee(e.target.value)} className="h-9 rounded-lg border border-border text-sm px-3 text-slate-600">
              <option value="all">All Owners</option>{members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          )}
        </div>
      </div>

      {!data ? <p className="text-slate-400">Loading…</p> : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3" data-testid="sales-stats">
            <Stat testid="stat-sales-leads" label="Leads" value={data.sales.leads} tone="text-slate-900" onClick={goStatus("")} />
            <Stat testid="stat-sales-outreach" label="Outreach" value={data.sales.outreach} tone="text-emerald-600" />
            <Stat testid="stat-sales-responses" label="Responses" value={data.sales.responses} tone="text-blue-600" />
            <Stat testid="stat-sales-demos" label="Demos" value={data.sales.demos} tone="text-purple-600" onClick={goStatus("Demo Booked")} />
            <Stat testid="stat-sales-trials" label="Trials" value={data.sales.trials} tone="text-teal-600" onClick={goStatus("Trial")} />
            <Stat testid="stat-sales-followups" label="Follow-ups" value={data.sales.follow_ups} tone="text-amber-600" />
            <Stat testid="stat-sales-invoices" label="Invoices" value={data.sales.invoices} tone="text-indigo-600" onClick={goStatus("Invoice Raised")} />
            <Stat testid="stat-sales-payments" label="Payments" value={data.sales.payments} tone="text-emerald-700" onClick={goStatus("Paid")} />
            <Stat testid="stat-sales-conversions" label="Conversions" value={data.sales.conversions} tone="text-emerald-600" onClick={goStatus("Converted")} />
            <Stat testid="stat-sales-losses" label="Losses" value={data.sales.losses} tone="text-rose-600" onClick={goStatus("Lost")} />
          </div>

          <Card className="p-5" data-testid="sales-funnel">
            <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
              <h3 className="font-bold text-slate-900">Sales Funnel</h3>
              <div data-testid="avg-days-demo-paid" className="text-xs bg-accent text-accent-foreground rounded-lg px-3 py-1.5 font-semibold">
                Avg days Demo Completed → Invoice Paid: <b>{data.avg_days_demo_to_paid == null ? "—" : `${data.avg_days_demo_to_paid} days`}</b>
                {data.avg_days_sample ? <span className="font-normal text-slate-500"> ({data.avg_days_sample} paid)</span> : null}
              </div>
            </div>
            <div className="space-y-2">
              {data.funnel.map((f, i) => (
                <button key={f.stage} data-testid={`funnel-step-${i}`} onClick={goStatus(f.status)} disabled={!f.status} className="w-full group">
                  <div className="flex items-center gap-3">
                    <span className="w-52 text-right text-xs font-medium text-slate-600 shrink-0">{f.stage}</span>
                    <div className="flex-1 h-8 bg-slate-100 rounded-md overflow-hidden">
                      <div className="h-full rounded-md flex items-center justify-end pr-2 text-white text-xs font-bold transition-all group-hover:brightness-95" style={{ width: `${Math.max(f.pct, 4)}%`, background: FUNNEL_COLORS[i % FUNNEL_COLORS.length] }}>{f.count}</div>
                    </div>
                    <span className="w-12 text-xs font-semibold text-slate-500 shrink-0">{f.pct}%</span>
                  </div>
                </button>
              ))}
            </div>
            <p className="text-xs text-slate-500 mt-3">Overall conversion: <b className="text-emerald-600">{data.funnel[0].count ? Math.round(data.sales.conversions / data.funnel[0].count * 100) : 0}%</b> · Lost/Closed in period: <button onClick={goStatus("Lost")} className="text-rose-600 font-semibold hover:underline">{data.lost}</button></p>
          </Card>

          <div className="grid lg:grid-cols-2 gap-6">
            <Card className="p-5" data-testid="chart-by-stage">
              <h3 className="font-bold text-slate-900 mb-4">Leads by Stage</h3>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={data.by_stage} margin={{ bottom: 60 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="stage" angle={-40} textAnchor="end" interval={0} tick={{ fontSize: 11 }} height={70} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11 }} /><Tooltip />
                  <Bar dataKey="count" fill="#E11D6B" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Card>
            <Card className="p-5" data-testid="chart-by-source">
              <h3 className="font-bold text-slate-900 mb-4">Lead Sources</h3>
              <ResponsiveContainer width="100%" height={280}>
                <PieChart>
                  <Pie data={data.by_source} dataKey="count" nameKey="source" cx="50%" cy="50%" outerRadius={90} label={(e) => e.source}>
                    {data.by_source.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie><Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </Card>
            <Card className="p-5" data-testid="chart-by-channel">
              <h3 className="font-bold text-slate-900 mb-4">Outreach by Channel</h3>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={data.by_channel}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="channel" tick={{ fontSize: 12 }} /><YAxis allowDecimals={false} tick={{ fontSize: 11 }} /><Tooltip />
                  <Bar dataKey="count" fill="#0D9488" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Card>
            {data.by_employee.length > 0 && (
              <Card className="p-5" data-testid="chart-by-employee">
                <h3 className="font-bold text-slate-900 mb-4">Outreach by Employee</h3>
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={data.by_employee} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} /><YAxis type="category" dataKey="name" tick={{ fontSize: 12 }} width={70} /><Tooltip />
                    <Bar dataKey="count" fill="#8B5CF6" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </Card>
            )}
            <Card className="p-5 lg:col-span-2" data-testid="chart-daily">
              <h3 className="font-bold text-slate-900 mb-4">Daily Activity</h3>
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={data.daily}>
                  <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="date" tick={{ fontSize: 11 }} /><YAxis allowDecimals={false} tick={{ fontSize: 11 }} /><Tooltip />
                  <Line type="monotone" dataKey="count" stroke="#E11D6B" strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
