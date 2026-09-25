import { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { useOptions } from "@/context/OptionsContext";
import { stageStyle, fmtDate } from "@/lib/crm";
import { toast } from "sonner";
import LeadDrawer from "@/components/LeadDrawer";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export default function Kanban() {
  const { labels } = useOptions();
  const stages = labels("stage");
  const lostReasons = labels("lost_reason");
  const stageOpts = useOptions().list("stage");
  const [leads, setLeads] = useState([]);
  const [members, setMembers] = useState([]);
  const [drag, setDrag] = useState(null);
  const [selected, setSelected] = useState(null);
  const [open, setOpen] = useState(false);
  const [lostPrompt, setLostPrompt] = useState(null);

  const load = () => api.get("/leads").then((r) => setLeads(r.data));
  useEffect(() => { load(); api.get("/users").then((r) => setMembers(r.data)).catch(() => {}); }, []);

  const move = async (lead, status, reason, notes) => {
    if (lead.status === status && !reason) return;
    const opt = stageOpts.find((o) => o.label === status);
    if (opt?.requires_reason && !reason) { setLostPrompt({ lead, status }); return; }
    setLeads((ls) => ls.map((l) => (l.id === lead.id ? { ...l, status } : l)));
    try { await api.patch(`/leads/${lead.id}/stage`, { status, lost_reason: reason, lost_notes: notes }); toast.success(`Moved ${lead.name} → ${status}`); load(); }
    catch (e) { toast.error(apiError(e)); load(); }
  };

  return (
    <div className="space-y-4">
      <div><p className="text-[11px] font-bold uppercase tracking-[0.16em] text-primary">Pipeline</p><h1 className="text-3xl font-extrabold tracking-tight text-slate-900">Kanban Board</h1><p className="text-sm text-slate-500 mt-1">Drag cards between stages to update status. Lost/closed stages ask for a reason.</p></div>
      <div className="flex gap-4 overflow-x-auto scrollbar-thin pb-4">
        {stages.map((stage) => {
          const items = leads.filter((l) => l.status === stage);
          return (
            <div key={stage} data-testid={`kanban-column-${stage.toLowerCase().replace(/ /g, "-")}`}
              onDragOver={(e) => e.preventDefault()} onDrop={() => drag && move(drag, stage)}
              className="w-72 shrink-0 rounded-xl bg-slate-100/70 p-3">
              <div className="flex items-center justify-between mb-3">
                <span className={`px-2 py-0.5 rounded-full text-xs font-semibold border ${stageStyle(stage)}`}>{stage}</span>
                <span className="text-xs font-bold text-slate-400">{items.length}</span>
              </div>
              <div className="space-y-2 min-h-[60px]">
                {items.map((l) => (
                  <div key={l.id} data-testid={`kanban-card-${l.id}`} draggable onDragStart={() => setDrag(l)} onDragEnd={() => setDrag(null)}
                    onClick={() => { setSelected(l.id); setOpen(true); }}
                    className="bg-white rounded-lg p-3 border border-border shadow-sm cursor-grab active:cursor-grabbing hover:shadow-md transition-shadow">
                    <p className="text-sm font-semibold text-slate-900">{l.name}</p>
                    <p className="text-xs text-slate-500">{l.practice}</p>
                    <div className="flex items-center justify-between mt-2 text-[11px] text-slate-400">
                      <span>{l.total_interactions || 0} touches</span>
                      {l.next_follow_up && <span>⏰ {fmtDate(l.next_follow_up)}</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
      <LeadDrawer leadId={selected} open={open} onOpenChange={setOpen} onChange={load} members={members} />
      {lostPrompt && <LostModal reasons={lostReasons} status={lostPrompt.status}
        onCancel={() => setLostPrompt(null)}
        onSubmit={(r, n) => { const lp = lostPrompt; setLostPrompt(null); move(lp.lead, lp.status, r, n); }} />}
    </div>
  );
}

function LostModal({ reasons, status, onCancel, onSubmit }) {
  const [reason, setReason] = useState(""); const [notes, setNotes] = useState("");
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" data-testid="kanban-lost-modal">
      <div className="bg-white rounded-xl p-6 w-full max-w-md space-y-4">
        <h3 className="font-bold text-slate-900">Reason required for "{status}"</h3>
        <Select value={reason} onValueChange={setReason}>
          <SelectTrigger data-testid="kanban-lost-reason"><SelectValue placeholder="Select a reason" /></SelectTrigger>
          <SelectContent>{reasons.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
        </Select>
        <textarea className="w-full border border-border rounded-lg p-2 text-sm" placeholder="Additional notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
        <div className="flex justify-end gap-2">
          <button className="px-3 py-2 text-sm rounded-lg border border-border" onClick={onCancel}>Cancel</button>
          <button data-testid="kanban-confirm-lost" disabled={!reason || (reason === "Other" && notes.trim().length < 3)} onClick={() => onSubmit(reason, notes)} className="px-3 py-2 text-sm rounded-lg bg-primary text-white disabled:opacity-50">Confirm</button>
        </div>
      </div>
    </div>
  );
}
