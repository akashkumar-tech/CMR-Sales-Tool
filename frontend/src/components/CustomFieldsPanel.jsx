import { useState } from "react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useOptions } from "@/context/OptionsContext";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Archive, ArchiveRestore, Plus } from "lucide-react";

const TYPES = ["text", "number", "date", "datetime", "longtext", "dropdown", "multiselect", "checkbox"];

export default function CustomFieldsPanel() {
  const { isAdmin } = useAuth();
  const { customFields, refresh } = useOptions();
  const [form, setForm] = useState({ label: "", type: "text", options: "", required: false, show_in_table: false });

  const add = async () => {
    if (!form.label) return toast.error("Label required");
    try {
      await api.post("/custom-fields", {
        label: form.label, type: form.type, required: form.required, show_in_table: form.show_in_table,
        options: ["dropdown", "multiselect"].includes(form.type) ? form.options.split(",").map((s) => s.trim()).filter(Boolean) : [],
      });
      toast.success("Custom field added"); setForm({ label: "", type: "text", options: "", required: false, show_in_table: false }); refresh();
    } catch (e) { toast.error(apiError(e)); }
  };
  const patch = async (cf, u) => { try { await api.patch(`/custom-fields/${cf.id}`, u); refresh(); } catch (e) { toast.error(apiError(e)); } };

  if (!isAdmin) return <Card className="p-6 text-sm text-slate-500">Only admins can manage custom fields.</Card>;

  return (
    <div className="grid md:grid-cols-2 gap-4">
      <Card className="p-5">
        <h3 className="font-bold text-slate-900 mb-3">Custom Fields</h3>
        <div className="space-y-2">
          {customFields.length === 0 && <p className="text-sm text-slate-400">No custom fields yet.</p>}
          {customFields.map((cf) => (
            <div key={cf.id} data-testid={`cf-row-${cf.id}`} className={`flex items-center justify-between text-sm px-2 py-2 rounded-lg ${cf.archived ? "opacity-40" : ""} bg-slate-50`}>
              <div><p className="font-semibold text-slate-800">{cf.label} <span className="text-[10px] text-slate-400">{cf.type}</span></p>{cf.options?.length ? <p className="text-xs text-slate-400">{cf.options.join(", ")}</p> : null}</div>
              <div className="flex items-center gap-2">
                {cf.show_in_table && <span className="text-[10px] text-primary">in table</span>}
                <button data-testid={`cf-archive-${cf.id}`} onClick={() => patch(cf, { archived: !cf.archived })} className="text-slate-400 hover:text-slate-700">{cf.archived ? <ArchiveRestore size={14} /> : <Archive size={14} />}</button>
              </div>
            </div>
          ))}
        </div>
      </Card>
      <Card className="p-5 space-y-3">
        <h3 className="font-bold text-slate-900">Add Field</h3>
        <div><Label>Label</Label><Input data-testid="cf-label-input" value={form.label} onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))} /></div>
        <div><Label>Type</Label>
          <Select value={form.type} onValueChange={(v) => setForm((f) => ({ ...f, type: v }))}>
            <SelectTrigger data-testid="cf-type-select"><SelectValue /></SelectTrigger>
            <SelectContent>{TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        {["dropdown", "multiselect"].includes(form.type) && (
          <div><Label>Options (comma separated)</Label><Input data-testid="cf-options-input" value={form.options} onChange={(e) => setForm((f) => ({ ...f, options: e.target.value }))} placeholder="Small, Medium, Large" /></div>
        )}
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm"><Checkbox checked={form.required} onCheckedChange={(v) => setForm((f) => ({ ...f, required: !!v }))} /> Required</label>
          <label className="flex items-center gap-2 text-sm"><Checkbox data-testid="cf-showtable" checked={form.show_in_table} onCheckedChange={(v) => setForm((f) => ({ ...f, show_in_table: !!v }))} /> Show in table</label>
        </div>
        <Button data-testid="cf-add-btn" onClick={add} className="w-full gap-1"><Plus size={14} /> Add Custom Field</Button>
      </Card>
    </div>
  );
}
