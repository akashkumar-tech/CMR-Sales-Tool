import { useState } from "react";
import { api, apiError } from "@/lib/api";
import { useOptions } from "@/context/OptionsContext";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const DEMO_STATUSES = ["Completed", "No-show", "Rescheduled", "Cancelled"];  // must match the demo_status options
const NEXT_ACTIONS = ["None", "Follow-up", "Pricing", "Invoice", "Payment follow-up", "Onboarding", "Client success"];
const PRIORITIES = ["Low", "Medium", "High", "Urgent"];
const EMPTY = { demo_status: "Completed", outcome: "", note: "", new_status: "", lost_reason: "", lost_notes: "", next_action: "None", next_owner_id: "", next_due_date: "", next_due_time: "", next_priority: "Medium" };

export default function DemoCompleteDialog({ leadId, leadName, open, onOpenChange, members = [], onDone }) {
  const { labels, list } = useOptions();
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const people = members.filter((m) => m.active !== false && m.role !== "admin");
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const needsOwner = form.next_action !== "None";
  const needsReason = !!list("stage").find((o) => o.label === form.new_status)?.requires_reason;
  const reasonOk = !needsReason || (form.lost_reason && (form.lost_reason !== "Other" || form.lost_notes.trim().length >= 3));

  const submit = async () => {
    if (needsOwner && !form.next_owner_id) return toast.error("Pick who owns the next action");
    if (!reasonOk) return toast.error(`A reason is required to move the lead to "${form.new_status}"`);
    setBusy(true);
    try {
      const payload = { ...form, new_status: form.new_status || null,
        lost_reason: needsReason ? form.lost_reason : null, lost_notes: needsReason ? form.lost_notes : null, next_action: form.next_action === "None" ? null : form.next_action, next_owner_id: needsOwner ? form.next_owner_id : null };
      await api.post(`/leads/${leadId}/demo/complete`, payload);
      toast.success(needsOwner ? "Demo updated & next action assigned" : "Demo outcome saved");
      onOpenChange(false); setForm(EMPTY); onDone?.();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white max-h-[90vh] overflow-y-auto" data-testid="demo-complete-dialog">
        <DialogHeader><DialogTitle>Demo outcome — {leadName}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Demo result</Label>
              <Select value={form.demo_status} onValueChange={(v) => set("demo_status", v)}>
                <SelectTrigger data-testid="demo-complete-status"><SelectValue /></SelectTrigger>
                <SelectContent>{DEMO_STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div><Label>Move lead to (optional)</Label>
              <Select value={form.new_status} onValueChange={(v) => set("new_status", v)}>
                <SelectTrigger data-testid="demo-complete-newstatus"><SelectValue placeholder="Keep current" /></SelectTrigger>
                <SelectContent>{labels("stage").map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          {needsReason && (
            <div className="rounded-lg border border-rose-200 bg-rose-50/50 p-3 space-y-2" data-testid="demo-complete-reason">
              <Label className="text-rose-700">Reason for "{form.new_status}" (required)</Label>
              <Select value={form.lost_reason} onValueChange={(v) => set("lost_reason", v)}>
                <SelectTrigger data-testid="demo-complete-reason-select"><SelectValue placeholder="Select a reason" /></SelectTrigger>
                <SelectContent>{labels("lost_reason").map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
              </Select>
              <Textarea placeholder={form.lost_reason === "Other" ? "Details (required for Other)" : "Additional notes (optional)"} value={form.lost_notes} onChange={(e) => set("lost_notes", e.target.value)} />
            </div>
          )}
          <div><Label>Outcome</Label><Input data-testid="demo-complete-outcome" value={form.outcome} onChange={(e) => set("outcome", e.target.value)} placeholder="e.g. Interested, wants pricing" /></div>
          <div><Label>Notes</Label><Textarea value={form.note} onChange={(e) => set("note", e.target.value)} /></div>

          <div className="rounded-lg border border-border p-3 space-y-3 bg-slate-50">
            <p className="text-xs font-bold uppercase tracking-wide text-primary">Next action</p>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>What next?</Label>
                <Select value={form.next_action} onValueChange={(v) => set("next_action", v)}>
                  <SelectTrigger data-testid="demo-complete-nextaction"><SelectValue /></SelectTrigger>
                  <SelectContent>{NEXT_ACTIONS.map((a) => <SelectItem key={a} value={a}>{a}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              {needsOwner && (
                <div><Label>Assign to</Label>
                  <Select value={form.next_owner_id} onValueChange={(v) => set("next_owner_id", v)}>
                    <SelectTrigger data-testid="demo-complete-nextowner"><SelectValue placeholder="Team member" /></SelectTrigger>
                    <SelectContent>{people.map((m) => <SelectItem key={m.id} value={m.id}>{m.name} · {m.role}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              )}
            </div>
            {needsOwner && (
              <div className="grid grid-cols-3 gap-3">
                <div><Label>Due date</Label><Input type="date" value={form.next_due_date} onChange={(e) => set("next_due_date", e.target.value)} /></div>
                <div><Label>Due time</Label><Input type="time" value={form.next_due_time} onChange={(e) => set("next_due_time", e.target.value)} /></div>
                <div><Label>Priority</Label>
                  <Select value={form.next_priority} onValueChange={(v) => set("next_priority", v)}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>{PRIORITIES.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              </div>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button data-testid="demo-complete-submit" onClick={submit} disabled={busy || !reasonOk}>{busy ? "Saving…" : "Save outcome"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
