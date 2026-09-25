import { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useOptions } from "@/context/OptionsContext";
import { stageStyle, fmtDate, fmtDateTime } from "@/lib/crm";
import { useAutoRefresh, relTime } from "@/lib/useAutoRefresh";
import { toast } from "sonner";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import CustomFieldInput from "@/components/CustomFieldInput";
import HandoverDialog from "@/components/HandoverDialog";
import DemoScheduleDialog from "@/components/DemoScheduleDialog";
import DemoCompleteDialog from "@/components/DemoCompleteDialog";
import { Clock, Trash2, UserPlus, RefreshCw, Activity as ActivityIcon, GitBranch, Pencil } from "lucide-react";

const KIND_STYLE = {
  activity: { dot: "bg-primary", icon: ActivityIcon },
  handover: { dot: "bg-violet-500", icon: GitBranch },
  change: { dot: "bg-slate-400", icon: Pencil },
};

export default function LeadDrawer({ leadId, open, onOpenChange, onChange, members = [], initialTab = "overview" }) {
  const { isManager } = useAuth();
  const { labels, customFields } = useOptions();
  const [lead, setLead] = useState(null);
  const [acts, setActs] = useState([]);
  const [timeline, setTimeline] = useState([]);
  const [history, setHistory] = useState({ audit: [], assignments: [] });
  const [tab, setTab] = useState(initialTab);
  const [act, setAct] = useState({ type: "Call", contact_method: "Phone Call", notes: "", outcome: "", next_action: "", next_follow_up: "", followup_done: false });
  const [lostPrompt, setLostPrompt] = useState(null);
  const [stale, setStale] = useState(false);
  const [handoverOpen, setHandoverOpen] = useState(false);
  const [demoSchedOpen, setDemoSchedOpen] = useState(false);
  const [demoCompOpen, setDemoCompOpen] = useState(false);
  const assignable = members.filter((m) => m.active !== false && m.role !== "admin");
  const memberName = (id) => members.find((m) => m.id === id)?.name || "—";
  const stageOpts = useOptions().list("stage");

  const loadTimeline = () => {
    api.get(`/activities?lead_id=${leadId}`).then((r) => setActs(r.data)).catch(() => {});
    api.get(`/leads/${leadId}/history`).then((r) => setHistory(r.data)).catch(() => {});
    api.get(`/leads/${leadId}/timeline`).then((r) => setTimeline(r.data.events || [])).catch(() => {});
  };

  const load = () => {
    if (!leadId) return;
    api.get(`/leads/${leadId}`).then((r) => { setLead(r.data); setStale(false); }).catch((e) => { toast.error(apiError(e)); onOpenChange(false); });
    loadTimeline();
  };
  useEffect(() => { if (open && leadId) { setTab(initialTab); load(); } }, [open, leadId]);

  // Real-time: quietly refresh display data + detect if someone else changed the lead.
  useAutoRefresh(() => {
    if (!open || !leadId) return;
    loadTimeline();
    api.get(`/leads/${leadId}`).then((r) => { if (lead && r.data.version !== lead.version) setStale(true); }).catch(() => {});
  }, 8000, open);

  const setField = (k, v) => setLead((l) => ({ ...l, [k]: v }));

  const payload = (extra = {}) => {
    const p = { name: lead.name, phone: lead.phone, email: lead.email, instagram: lead.instagram, linkedin: lead.linkedin,
      practice: lead.practice, location: lead.location, source: lead.source, status: lead.status, notes: lead.notes,
      next_follow_up: lead.next_follow_up, followup_assigned_to: lead.followup_assigned_to, demo_date: lead.demo_date,
      demo_time: lead.demo_time, demo_owner: lead.demo_owner, demo_status: lead.demo_status, invoice_status: lead.invoice_status,
      payment_status: lead.payment_status, invoice_owner: lead.invoice_owner, payment_owner: lead.payment_owner,
      invoice_amount: lead.invoice_amount, invoice_date: lead.invoice_date, payment_date: lead.payment_date,
      payment_reason: lead.payment_reason, response: lead.response, custom: lead.custom || {},
      expected_version: lead.version, ...extra };
    if (isManager) p.owner = lead.owner;
    return p;
  };

  const save = async (extra = {}) => {
    try {
      await api.put(`/leads/${leadId}`, payload(extra));
      toast.success("Lead updated"); load(); onChange?.();
    } catch (e) {
      const d = e?.response?.data?.detail;
      if (d?.requires_reason && d?.field === "payment") { toast.error(d.message); return; }
      if (d?.requires_reason) { setLostPrompt({ status: lead.status }); return; }
      // Only a version conflict means someone else changed the lead; other 409s are duplicate-contact errors.
      if (d?.conflict) { setStale(true); toast.error(d.message); return; }
      toast.error(apiError(e));
    }
  };

  const changeStatus = (v) => {
    const opt = stageOpts.find((o) => o.label === v);
    if (opt?.requires_reason) { setLostPrompt({ status: v }); return; }
    setField("status", v); save({ status: v });
  };

  const submitLost = async (reason, notes) => {
    try {
      // Save any unsaved edits first so the status change doesn't discard them.
      await api.put(`/leads/${leadId}`, payload());
      await api.patch(`/leads/${leadId}/stage`, { status: lostPrompt.status, lost_reason: reason, lost_notes: notes });
      toast.success("Status updated"); setLostPrompt(null); load(); onChange?.();
    } catch (e) {
      const d = e?.response?.data?.detail;
      if (d?.conflict) { setLostPrompt(null); setStale(true); }
      toast.error(apiError(e));
    }
  };

  const logActivity = async () => {
    if (!act.notes && !act.outcome) return toast.error("Add notes or an outcome");
    try {
      await api.post("/activities", { lead_id: leadId, ...act });
      toast.success("Interaction logged");
      setAct({ type: "Call", contact_method: "Phone Call", notes: "", outcome: "", next_action: "", next_follow_up: "", followup_done: false });
      load(); onChange?.();
    } catch (e) { toast.error(apiError(e)); }
  };

  const del = async () => {
    if (!window.confirm("Delete this lead?")) return;
    try { await api.delete(`/leads/${leadId}`); toast.success("Deleted"); onOpenChange(false); onChange?.(); }
    catch (e) { toast.error(apiError(e)); }
  };

  if (!lead) return <Sheet open={open} onOpenChange={onOpenChange}><SheetContent className="bg-white" /></Sheet>;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="bg-white w-full sm:max-w-xl overflow-y-auto p-0">
        <SheetHeader className="p-6 pb-3 border-b border-border">
          <div className="flex items-start justify-between gap-3">
            <div>
              <SheetTitle className="text-xl">{lead.name}</SheetTitle>
              <p className="text-sm text-slate-500">{lead.practice} {lead.location ? `· ${lead.location}` : ""}</p>
            </div>
            <Button size="sm" variant="outline" className="gap-1.5 shrink-0" data-testid="drawer-handover-btn" onClick={() => setHandoverOpen(true)}><UserPlus size={15} /> Assign</Button>
          </div>
          <div className="flex items-center gap-2 flex-wrap mt-1">
            <span className={`inline-flex w-fit px-2.5 py-1 rounded-full text-xs font-semibold border ${stageStyle(lead.status)}`}>{lead.status}</span>
            {lead.lost_reason && <span className="text-xs text-rose-600 font-medium">Reason: {lead.lost_reason}</span>}
            <span className="text-xs text-slate-400 flex items-center gap-1"><Clock size={12} /> {lead.total_interactions || 0} interactions · last {fmtDateTime(lead.last_interaction_at)}{lead.last_contacted_by_name ? ` by ${lead.last_contacted_by_name}` : ""}</span>
            <span className="text-[11px] text-slate-400" data-testid="lead-updated-indicator">updated {relTime(lead.updated_at)}</span>
          </div>
          {stale && (
            <div data-testid="stale-banner" className="mt-2 flex items-center justify-between gap-2 text-xs bg-amber-50 border border-amber-200 text-amber-800 rounded-lg px-3 py-2">
              <span>This lead was just updated by someone else.</span>
              <button onClick={load} className="inline-flex items-center gap-1 font-semibold hover:underline"><RefreshCw size={12} /> Reload</button>
            </div>
          )}
        </SheetHeader>
        <Tabs value={tab} onValueChange={setTab} className="p-6">
          <TabsList className="grid grid-cols-5 w-full">
            <TabsTrigger value="overview" data-testid="tab-overview">Info</TabsTrigger>
            <TabsTrigger value="log" data-testid="tab-log">Log</TabsTrigger>
            <TabsTrigger value="activity" data-testid="tab-timeline">Timeline</TabsTrigger>
            <TabsTrigger value="demo" data-testid="tab-demo">Demo</TabsTrigger>
            <TabsTrigger value="history" data-testid="tab-history">History</TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="space-y-3 mt-4">
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Phone</Label><Input value={lead.phone || ""} onChange={(e) => setField("phone", e.target.value)} /></div>
              <div><Label>Email</Label><Input value={lead.email || ""} onChange={(e) => setField("email", e.target.value)} /></div>
              <div><Label>Instagram</Label><Input value={lead.instagram || ""} onChange={(e) => setField("instagram", e.target.value)} /></div>
              <div><Label>LinkedIn</Label><Input value={lead.linkedin || ""} onChange={(e) => setField("linkedin", e.target.value)} /></div>
              <div><Label>Source</Label>
                <Select value={lead.source || ""} onValueChange={(v) => setField("source", v)}>
                  <SelectTrigger><SelectValue placeholder="—" /></SelectTrigger>
                  <SelectContent>{labels("source").map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div><Label>Status</Label>
                <Select value={lead.status} onValueChange={changeStatus}>
                  <SelectTrigger data-testid="drawer-status-select"><SelectValue /></SelectTrigger>
                  <SelectContent>{labels("stage").map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div><Label>Next Follow-up</Label><Input type="date" value={(lead.next_follow_up || "").slice(0, 10)} onChange={(e) => setField("next_follow_up", e.target.value)} /></div>
              <div><Label>Follow-up Assignee</Label>
                <Select value={lead.followup_assigned_to || ""} onValueChange={(v) => setField("followup_assigned_to", v)} disabled={!isManager}>
                  <SelectTrigger data-testid="drawer-followup-assign" title={isManager ? undefined : "Use Assign to hand this over"}><SelectValue placeholder="—" /></SelectTrigger>
                  <SelectContent>{assignable.map((m) => <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              {isManager && (
                <div className="col-span-2"><Label>Lead Owner</Label>
                  <Select value={lead.owner || ""} onValueChange={(v) => setField("owner", v)}>
                    <SelectTrigger data-testid="drawer-owner-select"><SelectValue /></SelectTrigger>
                    <SelectContent>{assignable.map((m) => <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              )}
              <div className="col-span-2"><Label>Notes</Label><Textarea value={lead.notes || ""} onChange={(e) => setField("notes", e.target.value)} /></div>
              {customFields.map((f) => <CustomFieldInput key={f.id} field={f} value={(lead.custom || {})[f.key]} onChange={(k, v) => setField("custom", { ...(lead.custom || {}), [k]: v })} className={f.type === "longtext" || f.type === "multiselect" ? "col-span-2" : ""} />)}
            </div>
            <div className="flex justify-between pt-2">
              {isManager ? <Button variant="outline" className="text-destructive gap-2" onClick={del} data-testid="delete-lead-btn"><Trash2 size={16} /> Delete</Button> : <span />}
              <Button data-testid="save-drawer-btn" onClick={() => save()}>Save Changes</Button>
            </div>
          </TabsContent>

          <TabsContent value="log" className="mt-4 space-y-3">
            <div><Label>Contact Method</Label>
              <Select value={act.contact_method} onValueChange={(v) => setAct((a) => ({ ...a, contact_method: v, type: v === "Phone Call" ? "Call" : v }))}>
                <SelectTrigger data-testid="activity-method-select"><SelectValue /></SelectTrigger>
                <SelectContent>{labels("contact_method").map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div><Label>Activity Type</Label>
              <Select value={act.type} onValueChange={(v) => setAct((a) => ({ ...a, type: v }))}>
                <SelectTrigger data-testid="activity-type-select"><SelectValue /></SelectTrigger>
                <SelectContent>{labels("activity_type").map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div><Label>Outcome</Label><Input data-testid="activity-outcome-input" value={act.outcome} onChange={(e) => setAct((a) => ({ ...a, outcome: e.target.value }))} /></div>
            <div><Label>Notes</Label><Textarea data-testid="activity-notes-input" value={act.notes} onChange={(e) => setAct((a) => ({ ...a, notes: e.target.value }))} /></div>
            <div><Label>Next Action</Label><Input value={act.next_action} onChange={(e) => setAct((a) => ({ ...a, next_action: e.target.value }))} /></div>
            {lead.next_follow_up && (
              <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer select-none" data-testid="activity-followup-done">
                <input type="checkbox" checked={act.followup_done} onChange={(e) => setAct((a) => ({ ...a, followup_done: e.target.checked }))} />
                Mark the current follow-up ({fmtDate(lead.next_follow_up)}) as done
              </label>
            )}
            <div><Label>{act.followup_done ? "Next Follow-up Date (optional)" : "Next Follow-up Date"}</Label><Input type="date" value={act.next_follow_up} onChange={(e) => setAct((a) => ({ ...a, next_follow_up: e.target.value }))} /></div>
            <Button data-testid="save-activity-btn" onClick={logActivity} className="w-full">Log Interaction</Button>
          </TabsContent>

          <TabsContent value="activity" className="mt-4">
            <div className="space-y-1" data-testid="lead-timeline">
              {timeline.length === 0 && <p className="text-sm text-slate-400">No activity yet.</p>}
              {timeline.map((e, i) => {
                const st = KIND_STYLE[e.kind] || KIND_STYLE.change;
                const Icon = st.icon;
                return (
                  <div key={i} className="flex gap-3 pb-4 relative" data-testid={`timeline-event-${i}`}>
                    <div className="flex flex-col items-center">
                      <span className={`h-6 w-6 rounded-full grid place-items-center text-white ${st.dot}`}><Icon size={12} /></span>
                      {i < timeline.length - 1 && <span className="w-px flex-1 bg-border mt-1" />}
                    </div>
                    <div className="flex-1 -mt-0.5">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-semibold text-slate-800">{e.actor}</span>
                        <span className="text-[11px] text-slate-400">{fmtDateTime(e.timestamp)}</span>
                      </div>
                      <p className="text-sm text-slate-600">{e.text}</p>
                      {e.detail && <p className="text-xs text-slate-500 mt-0.5">{e.detail}</p>}
                    </div>
                  </div>
                );
              })}
            </div>
          </TabsContent>

          <TabsContent value="demo" className="mt-4 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Demo Date</Label><Input type="date" value={(lead.demo_date || "").slice(0, 10)} onChange={(e) => setField("demo_date", e.target.value)} /></div>
              <div><Label>Demo Time</Label><Input type="time" value={lead.demo_time || ""} onChange={(e) => setField("demo_time", e.target.value)} /></div>
              <div><Label>Demo Owner (Taken by)</Label>
                <Select value={lead.demo_owner || ""} onValueChange={(v) => setField("demo_owner", v)} disabled={!isManager}>
                  <SelectTrigger data-testid="drawer-demo-owner" title={isManager ? undefined : "Use Schedule / assign presenter"}><SelectValue placeholder="—" /></SelectTrigger>
                  <SelectContent>{assignable.map((m) => <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div><Label>Demo Status</Label>
                <Select value={lead.demo_status || ""} onValueChange={(v) => setField("demo_status", v)}>
                  <SelectTrigger data-testid="drawer-demo-status"><SelectValue placeholder="—" /></SelectTrigger>
                  <SelectContent>{labels("demo_status").map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div><Label>Invoice Status</Label>
                <Select value={lead.invoice_status || ""} onValueChange={(v) => setField("invoice_status", v)}>
                  <SelectTrigger><SelectValue placeholder="—" /></SelectTrigger>
                  <SelectContent>{labels("invoice_status").map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div><Label>Payment Status</Label>
                <Select value={lead.payment_status || ""} onValueChange={(v) => setField("payment_status", v)}>
                  <SelectTrigger><SelectValue placeholder="—" /></SelectTrigger>
                  <SelectContent>{labels("payment_status").map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div><Label>Invoice Amount</Label><Input type="number" data-testid="drawer-invoice-amount" value={lead.invoice_amount ?? ""} onChange={(e) => setField("invoice_amount", e.target.value === "" ? null : Number(e.target.value))} /></div>
              <div><Label>Invoice Date</Label><Input type="date" value={(lead.invoice_date || "").slice(0, 10)} onChange={(e) => setField("invoice_date", e.target.value)} /></div>
              <div><Label>Payment Date</Label><Input type="date" value={(lead.payment_date || "").slice(0, 10)} onChange={(e) => setField("payment_date", e.target.value)} /></div>
              <div><Label>Invoice Owner</Label>
                <Select value={lead.invoice_owner || ""} onValueChange={(v) => setField("invoice_owner", v)}>
                  <SelectTrigger><SelectValue placeholder="—" /></SelectTrigger>
                  <SelectContent>{assignable.map((m) => <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              {lead.payment_status === "Not Paid" && (
                <div className="col-span-2"><Label className="text-rose-600">Reason for Not Paid (required)</Label><Input data-testid="drawer-payment-reason" value={lead.payment_reason || ""} onChange={(e) => setField("payment_reason", e.target.value)} placeholder="e.g. Payment link issue, client delayed" /></div>
              )}
            </div>
            <div className="flex gap-2">
              <Button variant="outline" className="flex-1" data-testid="drawer-schedule-demo-btn" onClick={() => setDemoSchedOpen(true)}>Schedule / assign presenter</Button>
              <Button variant="outline" className="flex-1" data-testid="drawer-complete-demo-btn" disabled={!lead.demo_date} onClick={() => setDemoCompOpen(true)}>Demo outcome…</Button>
            </div>
            <Button onClick={() => save()} className="w-full">Save Demo & Payment</Button>
          </TabsContent>

          <TabsContent value="history" className="mt-4 space-y-4">
            <div>
              <p className="text-xs font-bold uppercase tracking-wide text-slate-400 mb-2">Assignment trail</p>
              {history.assignments.length === 0 && <p className="text-sm text-slate-400">No reassignments yet.</p>}
              {history.assignments.map((a) => {
                const fieldLabel = { owner: "Lead owner", followup_assigned_to: "Follow-up", follow_up: "Follow-up", demo_owner: "Demo owner", demo: "Demo", presales: "Pre-sales", sales: "Sales", pricing: "Pricing", invoice: "Invoice", payment: "Payment", onboarding: "Onboarding", success: "Client success", other: "Task" }[a.field] || a.field;
                return (
                  <div key={a.id} className="text-xs text-slate-600 border-b border-border pb-1.5" data-testid={`assignment-${a.id}`}>
                    <b className="text-slate-800">{fieldLabel}</b>: {memberName(a.from)} → {memberName(a.to)} <span className="text-slate-400">by {a.by_name}</span>
                    <span className="text-slate-400 float-right">{fmtDateTime(a.timestamp)}</span>
                    {a.note && <p className="text-slate-500 italic">“{a.note}”</p>}
                  </div>
                );
              })}
            </div>
            <div>
              <p className="text-xs font-bold uppercase tracking-wide text-slate-400 mb-2">Change log</p>
              {history.audit.length === 0 && <p className="text-sm text-slate-400">No history yet.</p>}
              {history.audit.map((h) => (
                <div key={h.id} className="text-xs text-slate-600 border-b border-border pb-1.5">
                  <b className="text-slate-800">{h.actor_name}</b> {h.action} {h.field}{h.prev || h.new ? `: ${h.prev || "—"} → ${h.new}` : ""}
                  <span className="text-slate-400 float-right">{fmtDateTime(h.timestamp)}</span>
                </div>
              ))}
            </div>
          </TabsContent>
        </Tabs>

        <HandoverDialog leadId={leadId} leadName={lead.name} open={handoverOpen} onOpenChange={setHandoverOpen} members={members} onDone={() => { load(); onChange?.(); }} />
        <DemoScheduleDialog leadId={leadId} leadName={lead.name} open={demoSchedOpen} onOpenChange={setDemoSchedOpen} members={members} onDone={() => { load(); onChange?.(); }} />
        <DemoCompleteDialog leadId={leadId} leadName={lead.name} open={demoCompOpen} onOpenChange={setDemoCompOpen} members={members} onDone={() => { load(); onChange?.(); }} />
        {lostPrompt && <LostReasonModal reasons={labels("lost_reason")} onCancel={() => setLostPrompt(null)} onSubmit={submitLost} status={lostPrompt.status} />}
      </SheetContent>
    </Sheet>
  );
}

function LostReasonModal({ reasons, onCancel, onSubmit, status }) {
  const [reason, setReason] = useState("");
  const [notes, setNotes] = useState("");
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" data-testid="lost-reason-modal">
      <div className="bg-white rounded-xl p-6 w-full max-w-md space-y-4">
        <h3 className="font-bold text-slate-900">Reason required for "{status}"</h3>
        <p className="text-xs text-slate-500 -mt-2">You can't save this status without a reason.</p>
        <Select value={reason} onValueChange={setReason}>
          <SelectTrigger data-testid="lost-reason-select"><SelectValue placeholder="Select a reason" /></SelectTrigger>
          <SelectContent>{reasons.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
        </Select>
        <Textarea placeholder="Additional notes (optional)" value={notes} onChange={(e) => setNotes(e.target.value)} data-testid="lost-notes-input" />
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onCancel}>Cancel</Button>
          <Button data-testid="confirm-lost-btn" disabled={!reason || (reason === "Other" && notes.trim().length < 3)} onClick={() => onSubmit(reason, notes)}>Confirm</Button>
        </div>
      </div>
    </div>
  );
}
