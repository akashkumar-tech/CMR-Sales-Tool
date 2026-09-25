import { useState } from "react";
import { api, apiError } from "@/lib/api";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const EMPTY = { demo_date: "", demo_time: "", presenter_id: "", note: "" };

export default function DemoScheduleDialog({ leadId, leadName, open, onOpenChange, members = [], onDone }) {
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const presenters = members.filter((m) => m.active !== false && m.role !== "admin");
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    if (!form.demo_date) return toast.error("Pick a demo date");
    if (!form.presenter_id) return toast.error("Pick a presenter");
    setBusy(true);
    try {
      await api.post(`/leads/${leadId}/demo/schedule`, form);
      toast.success("Demo scheduled — presenter notified & task created");
      onOpenChange(false); setForm(EMPTY); onDone?.();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white" data-testid="demo-schedule-dialog">
        <DialogHeader><DialogTitle>Schedule demo — {leadName}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Demo date</Label><Input type="date" data-testid="demo-sched-date" value={form.demo_date} onChange={(e) => set("demo_date", e.target.value)} /></div>
            <div><Label>Demo time</Label><Input type="time" value={form.demo_time} onChange={(e) => set("demo_time", e.target.value)} /></div>
          </div>
          <div><Label>Presenter (conducted by)</Label>
            <Select value={form.presenter_id} onValueChange={(v) => set("presenter_id", v)}>
              <SelectTrigger data-testid="demo-sched-presenter"><SelectValue placeholder="Assign a presenter" /></SelectTrigger>
              <SelectContent>{presenters.map((m) => <SelectItem key={m.id} value={m.id}>{m.name} · {m.role}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div><Label>Instructions / note</Label><Textarea data-testid="demo-sched-note" value={form.note} onChange={(e) => set("note", e.target.value)} placeholder="Anything the presenter should know" /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button data-testid="demo-sched-submit" onClick={submit} disabled={busy}>{busy ? "Scheduling…" : "Schedule & notify"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
