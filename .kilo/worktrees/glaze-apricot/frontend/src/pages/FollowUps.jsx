import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { stageStyle, fmtDate } from "@/lib/crm";
import { useAutoRefresh } from "@/lib/useAutoRefresh";
import LeadDrawer from "@/components/LeadDrawer";
import { Card } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

const VIEWS = [["today", "Today"], ["upcoming", "Upcoming"], ["overdue", "Overdue"], ["all", "All Open"]];

export default function FollowUps() {
  const [view, setView] = useState("today");
  const [leads, setLeads] = useState([]);
  const [members, setMembers] = useState([]);
  const [selected, setSelected] = useState(null);
  const [open, setOpen] = useState(false);

  const load = useCallback(() => {
    const p = new URLSearchParams({ scope: "mine" });
    if (view !== "all") p.set("follow_up", view);
    api.get(`/leads?${p.toString()}`).then((r) => {
      let rows = r.data.filter((l) => l.next_follow_up);
      if (view === "all") rows = rows.filter((l) => !["Converted", "Lost", "Closed", "Not Interested"].includes(l.status));
      rows.sort((a, b) => (a.next_follow_up || "").localeCompare(b.next_follow_up || ""));
      setLeads(rows);
    }).catch(() => {});
  }, [view]);
  useEffect(() => { load(); }, [load]);
  useAutoRefresh(load, 10000);
  useEffect(() => { api.get("/users").then((r) => setMembers(r.data)).catch(() => {}); }, []);
  const memberName = (id) => members.find((m) => m.id === id)?.name || "—";

  return (
    <div className="space-y-5">
      <div><p className="text-[11px] font-bold uppercase tracking-[0.16em] text-primary">Schedule</p><h1 className="text-3xl font-extrabold tracking-tight text-slate-900">Follow-ups</h1><p className="text-sm text-slate-500 mt-1">Everything you owe a contact, sorted by date.</p></div>
      <Tabs value={view} onValueChange={setView}><TabsList>{VIEWS.map(([v, l]) => <TabsTrigger key={v} value={v} data-testid={`followup-view-${v}`}>{l}</TabsTrigger>)}</TabsList></Tabs>
      <Card className="divide-y divide-border">
        {leads.map((l) => (
          <button key={l.id} data-testid={`followup-row-${l.id}`} onClick={() => { setSelected(l.id); setOpen(true); }} className="w-full text-left flex items-center gap-4 p-4 hover:bg-slate-50">
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-slate-900 truncate">{l.name}</p>
              <p className="text-xs text-slate-500 truncate">{l.practice} · owner {memberName(l.followup_assigned_to)}</p>
            </div>
            <span className="text-xs text-slate-500">{fmtDate(l.next_follow_up)}</span>
            <span className={`text-xs px-2 py-0.5 rounded-full border ${stageStyle(l.status)}`}>{l.status}</span>
          </button>
        ))}
        {leads.length === 0 && <div className="p-10 text-center text-slate-400 text-sm">No follow-ups here. 🎯</div>}
      </Card>
      <LeadDrawer leadId={selected} open={open} onOpenChange={setOpen} onChange={load} members={members} />
    </div>
  );
}
