import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useOptions } from "@/context/OptionsContext";
import { stageStyle, fmtDateTime } from "@/lib/crm";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import CustomFieldInput from "@/components/CustomFieldInput";
import { AlertTriangle } from "lucide-react";

const empty = { name: "", phone: "", email: "", instagram: "", linkedin: "", practice: "", location: "", source: "", status: "New Lead", next_follow_up: "", notes: "", owner: "", custom: {} };

export default function AddLeadDialog({ open, onOpenChange, onCreated, members = [] }) {
  const { isManager } = useAuth();
  const { labels, customFields } = useOptions();
  const [form, setForm] = useState(empty);
  const [dupes, setDupes] = useState([]);
  const [saving, setSaving] = useState(false);
  const assignable = members.filter((m) => m.active !== false && m.role !== "admin");

  useEffect(() => { if (open) { setForm(empty); setDupes([]); } }, [open]);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const setCustom = (k, v) => setForm((f) => ({ ...f, custom: { ...f.custom, [k]: v } }));

  const checkDup = async () => {
    if (!form.phone && !form.email && !form.instagram && !form.linkedin) return;
    try {
      const { data } = await api.post("/leads/check-duplicate", { phone: form.phone, email: form.email, instagram: form.instagram, linkedin: form.linkedin });
      setDupes(data.duplicates);
    } catch {}
  };

  const submit = async () => {
    if (!form.name.trim()) return toast.error("Lead name is required");
    const blank = (v) => v === undefined || v === null || (typeof v === "string" && !v.trim()) || (Array.isArray(v) && !v.length);
    const missing = customFields.filter((f) => f.required && blank(form.custom?.[f.key])).map((f) => f.label);
    if (missing.length) return toast.error(`Please fill in required field(s): ${missing.join(", ")}`);
    if (dupes.find((d) => d.matched_on?.some((m) => m === "phone" || m === "email"))) { toast.error("This phone/email already exists. Open the existing lead instead."); return; }
    setSaving(true);
    try {
      const payload = { ...form }; if (!isManager) delete payload.owner;
      const { data } = await api.post("/leads", payload);
      toast.success("Lead added"); onOpenChange(false); onCreated?.(data.id);
    } catch (e) {
      const d = e?.response?.data?.detail;
      if (e?.response?.status === 409 && d?.existing_id) { toast.error(d.message || "Duplicate lead"); setDupes([{ id: d.existing_id, name: d.existing_name, matched_on: ["phone/email"] }]); }
      else toast.error(apiError(e));
    } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto bg-white">
        <DialogHeader><DialogTitle>Add New Lead</DialogTitle></DialogHeader>
        {dupes.length > 0 && (
          <div data-testid="duplicate-warning-banner" className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 space-y-2">
            <div className="flex gap-2 font-semibold"><AlertTriangle size={18} className="shrink-0" /> Existing lead found. This contact already exists in the CRM.</div>
            {dupes.map((d) => (
              <div key={d.id} className="flex items-center justify-between bg-white rounded-md p-2 border border-amber-200">
                <div>
                  <p className="font-semibold text-slate-900">{d.name} {d.status && <span className={`ml-1 text-[11px] px-2 py-0.5 rounded-full border ${stageStyle(d.status)}`}>{d.status}</span>}</p>
                  <p className="text-xs text-slate-500">Matched on {(d.matched_on || []).join(", ")} · owner: {d.owner_name || "—"}{d.last_contacted_by ? ` · last by ${d.last_contacted_by}` : ""}{d.last_interaction_at ? ` (${fmtDateTime(d.last_interaction_at)})` : ""}</p>
                </div>
                <Button size="sm" variant="outline" data-testid={`open-existing-${d.id}`} onClick={() => { onOpenChange(false); onCreated?.(d.id); }}>Open Existing Lead</Button>
              </div>
            ))}
          </div>
        )}
        <div className="grid grid-cols-2 gap-4">
          <div><Label>Lead Name *</Label><Input data-testid="lead-name-input" value={form.name} onChange={(e) => set("name", e.target.value)} /></div>
          <div><Label>Practice / Clinic</Label><Input data-testid="lead-practice-input" value={form.practice} onChange={(e) => set("practice", e.target.value)} /></div>
          <div><Label>Phone / WhatsApp</Label><Input data-testid="lead-phone-input" value={form.phone} onChange={(e) => set("phone", e.target.value)} onBlur={checkDup} /></div>
          <div><Label>Email</Label><Input data-testid="lead-email-input" value={form.email} onChange={(e) => set("email", e.target.value)} onBlur={checkDup} /></div>
          <div><Label>Instagram</Label><Input data-testid="lead-instagram-input" value={form.instagram} onChange={(e) => set("instagram", e.target.value)} onBlur={checkDup} /></div>
          <div><Label>LinkedIn</Label><Input data-testid="lead-linkedin-input" value={form.linkedin} onChange={(e) => set("linkedin", e.target.value)} onBlur={checkDup} /></div>
          <div><Label>Location</Label><Input data-testid="lead-location-input" value={form.location} onChange={(e) => set("location", e.target.value)} /></div>
          <div><Label>Source</Label>
            <Select value={form.source} onValueChange={(v) => set("source", v)}>
              <SelectTrigger data-testid="lead-source-select"><SelectValue placeholder="Select source" /></SelectTrigger>
              <SelectContent>{labels("source").map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div><Label>Status</Label>
            <Select value={form.status} onValueChange={(v) => set("status", v)}>
              <SelectTrigger data-testid="lead-status-select"><SelectValue /></SelectTrigger>
              <SelectContent>{labels("stage").map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div><Label>Next Follow-up</Label><Input type="date" data-testid="lead-followup-input" value={form.next_follow_up} onChange={(e) => set("next_follow_up", e.target.value)} /></div>
          {isManager && (
            <div><Label>Lead Owner</Label>
              <Select value={form.owner} onValueChange={(v) => set("owner", v)}>
                <SelectTrigger data-testid="lead-owner-select"><SelectValue placeholder="Default: you" /></SelectTrigger>
                <SelectContent>{assignable.map((m) => <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          )}
          <div className="col-span-2"><Label>Notes</Label><Textarea data-testid="lead-notes-input" value={form.notes} onChange={(e) => set("notes", e.target.value)} /></div>
          {customFields.map((f) => <CustomFieldInput key={f.id} field={f} value={form.custom?.[f.key]} onChange={setCustom} className={f.type === "longtext" || f.type === "multiselect" ? "col-span-2" : ""} />)}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button data-testid="save-lead-btn" onClick={submit} disabled={saving}>{saving ? "Saving…" : "Add Lead"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
