import { Card } from "@/components/ui/card";

const FUNNEL_COLORS = ["#6366F1", "#4F46E5", "#7C3AED", "#8B5CF6", "#A855F7", "#C026D3", "#D946EF", "#EC4899", "#F43F5E", "#10B981"];
// Statuses counted as losses by the backend (LOST_STATUSES in server.py) — the drill-down must list all of them.
export const LOST_STATUSES = "Lost,Not Interested,Closed";

// The Sales Funnel card, drawn from a GET /reports response (funnel, sales, lost, avg days) — shared by Reports and
// the Dashboard so both show the backend's numbers, never a separate calculation.
// onStep(step) / onLost: click handlers for a funnel step and the Lost/Closed count. filters: optional controls shown
// under the title (the Dashboard's Period / Team / Owner; Reports keeps its filters in the page header).
export default function SalesFunnel({ data, onStep, onLost, subtitle, filters, labelClass = "w-52", testid = "sales-funnel" }) {
  return (
    <Card className="p-5" data-testid={testid}>
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div>
          <h3 className="font-bold text-slate-900">Sales Funnel</h3>
          {subtitle && <p className="text-xs text-slate-500">{subtitle}</p>}
        </div>
        <div data-testid="avg-days-demo-paid" className="text-xs bg-accent text-accent-foreground rounded-lg px-3 py-1.5 font-semibold">
          Avg days Demo Completed → Invoice Paid: <b>{data.avg_days_demo_to_paid == null ? "—" : `${data.avg_days_demo_to_paid} days`}</b>
          {data.avg_days_sample ? <span className="font-normal text-slate-500"> ({data.avg_days_sample} paid)</span> : null}
        </div>
      </div>
      {filters && <div className="flex items-center gap-2 flex-wrap mb-4">{filters}</div>}
      <div className="space-y-2">
        {data.funnel.map((f, i) => (
          <button key={f.stage} data-testid={`funnel-step-${i}`} onClick={onStep(f)} className="w-full group">
            <div className="flex items-center gap-3">
              <span className={`${labelClass} text-right text-xs font-medium text-slate-600 shrink-0`}>{f.stage}</span>
              <div className="flex-1 h-8 bg-slate-100 rounded-md overflow-hidden">
                <div className="h-full rounded-md flex items-center justify-end pr-2 text-white text-xs font-bold transition-all group-hover:brightness-95" style={{ width: `${Math.max(f.pct, 4)}%`, background: FUNNEL_COLORS[i % FUNNEL_COLORS.length] }}>{f.count}</div>
              </div>
              <span className="w-12 text-xs font-semibold text-slate-500 shrink-0">{f.pct}%</span>
            </div>
          </button>
        ))}
      </div>
      <p className="text-xs text-slate-500 mt-3">Overall conversion: <b className="text-emerald-600">{data.sales.overall_conversion}%</b> · Lost/Closed in period: <button onClick={onLost} className="text-rose-600 font-semibold hover:underline">{data.lost}</button></p>
    </Card>
  );
}
