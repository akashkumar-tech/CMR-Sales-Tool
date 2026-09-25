import { useState } from "react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const RESP = [
  ["owner", "Lead ownership"], ["presales", "Pre-sales"], ["sales", "Sales"], ["demo", "Demo"],
  ["follow_up", "Follow-up"], ["pricing", "Pricing"], ["invoice", "Invoice"], ["payment", "Payment follow-up"],
  ["onboarding", "Client onboarding"], ["success", "Client success"], ["other", "Other task"],
];
const PRIORITIES = ["Low", "Medium", "High", "Urgent"];
const EMPTY = { responsibility: "follow_up", assignee_id: "", due_date: "", due_time: "", priority: "Medium", note: "" };

export default function HandoverDialog({ leadId, leadName, open, onOpenChange, members = [], onDone }) {
  const { isManager } = useAuth();
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const assignable = members.filter((m) => m.active !== false && m.role !== "admin");
  const options = isManager ? RESP : RESP.filter((r) => r[0] !== "owner");
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    if (!form.assignee_id) return toast.error("Pick who to assign to");
    setBusy(true);
    try {
      await api.post(`/leads/${leadId}/handover`, form);
      toast.success("Assigned — the team member has been notified by app + email");
      onOpenChange(false);
      setForm(EMPTY);
      onDone?.();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white" data-testid="handover-dialog">
        <DialogHeader><DialogTitle>Assign / Handover — {leadName}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div><Label>Responsibility</Label>
            <Select value={form.responsibility} onValueChange={(v) => set("responsibility", v)}>
              <SelectTrigger data-testid="handover-responsibility"><SelectValue /></SelectTrigger>
              <SelectContent>{options.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div><Label>Assign to</Label>
            <Select value={form.assignee_id} onValueChange={(v) => set("assignee_id", v)}>
              <SelectTrigger data-testid="handover-assignee"><SelectValue placeholder="Select team member" /></SelectTrigger>
              <SelectContent>{assignable.map((m) => <SelectItem key={m.id} value={m.id}>{m.name} · {m.role}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div><Label>Due date</Label><Input type="date" data-testid="handover-due-date" value={form.due_date} onChange={(e) => set("due_date", e.target.value)} /></div>
            <div><Label>Due time</Label><Input type="time" value={form.due_time} onChange={(e) => set("due_time", e.target.value)} /></div>
            <div><Label>Priority</Label>
              <Select value={form.priority} onValueChange={(v) => set("priority", v)}>
                <SelectTrigger data-testid="handover-priority"><SelectValue /></SelectTrigger>
                <SelectContent>{PRIORITIES.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          <div><Label>Instructions / note</Label><Textarea data-testid="handover-note" value={form.note} onChange={(e) => set("note", e.target.value)} placeholder="What needs to happen?" /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button data-testid="handover-submit-btn" onClick={submit} disabled={busy}>{busy ? "Assigning…" : "Assign & notify"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
