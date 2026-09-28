import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/crm";
import { Card } from "@/components/ui/card";
import { Phone, MessageCircle, Instagram, Mail, StickyNote, Calendar, RefreshCw, X } from "lucide-react";

const ICONS = { Call: Phone, WhatsApp: MessageCircle, Instagram, Email: Mail, Note: StickyNote, Demo: Calendar, "Follow-up": RefreshCw, "Stage Change": RefreshCw };
const PERIODS = { today: "today", week: "this week", month: "this month", quarter: "this quarter", year: "this year" };

export default function Activities() {
  const [params, setParams] = useSearchParams();
  const [acts, setActs] = useState([]);
  // Filters come from the dashboard tiles (e.g. ?type=Call&period=month&staff=1).
  const type = params.get("type") || "";
  const period = params.get("period") || "";
  useEffect(() => { api.get(`/activities?${params.toString()}`).then((r) => setActs(r.data)); }, [params]);

  return (
    <div className="space-y-5">
      <div><p className="text-[11px] font-bold uppercase tracking-[0.16em] text-primary">Timeline</p><h1 className="text-3xl font-extrabold tracking-tight text-slate-900">Activities</h1></div>
      {(type || period) && (
        <div data-testid="activity-filter" className="flex items-center gap-2 text-sm text-slate-600">
          <span>Showing <b className="text-slate-900">{type ? type.split(",").join(", ") : "all"}</b> activities{period ? ` ${PERIODS[period] || ""}` : ""} · {acts.length}</span>
          <button data-testid="clear-activity-filter" onClick={() => setParams({})} className="inline-flex items-center gap-1 text-xs text-primary hover:underline"><X size={12} /> Clear</button>
        </div>
      )}
      <Card className="p-6">
        <div className="space-y-4">
          {acts.map((a) => {
            const Icon = ICONS[a.type] || StickyNote;
            return (
              <div key={a.id} data-testid={`activity-${a.id}`} className="flex gap-3">
                <div className="h-9 w-9 rounded-full bg-primary/10 text-primary grid place-items-center shrink-0"><Icon size={16} /></div>
                <div className="flex-1 border-b border-border pb-4">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-semibold text-slate-900">{a.type} · {a.lead_name}</p>
                    <span className="text-xs text-slate-400">{fmtDate(a.timestamp)}</span>
                  </div>
                  {a.notes && <p className="text-sm text-slate-600">{a.notes}</p>}
                  {a.outcome && <p className="text-xs text-emerald-600">Outcome: {a.outcome}</p>}
                  {a.next_action && <p className="text-xs text-slate-500">Next: {a.next_action}</p>}
                  <p className="text-[11px] text-slate-400 mt-0.5">by {a.employee_name}</p>
                </div>
              </div>
            );
          })}
          {acts.length === 0 && <p className="text-sm text-slate-400 text-center py-8">No activities {type || period ? "match this filter" : "yet"}.</p>}
        </div>
      </Card>
    </div>
  );
}
