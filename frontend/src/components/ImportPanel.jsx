import { useRef, useState } from "react";
import { api, apiError } from "@/lib/api";
import { useOptions } from "@/context/OptionsContext";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Upload, FileSpreadsheet } from "lucide-react";

const CRM_FIELDS = [
  ["name", "Lead Name"], ["phone", "Phone"], ["email", "Email"], ["instagram", "Instagram"],
  ["linkedin", "LinkedIn"], ["practice", "Practice / Clinic"], ["location", "Location"],
  ["source", "Source"], ["status", "Status"], ["notes", "Notes"],
];

function guess(col) {
  const c = col.toLowerCase();
  if (c.includes("name")) return "name";
  if (c.includes("phone") || c.includes("mobile") || c.includes("whatsapp")) return "phone";
  if (c.includes("mail")) return "email";
  if (c.includes("insta") || c === "ig") return "instagram";
  if (c.includes("linkedin")) return "linkedin";
  if (c.includes("practice") || c.includes("clinic")) return "practice";
  if (c.includes("location") || c.includes("city")) return "location";
  if (c.includes("source")) return "source";
  if (c.includes("status") || c.includes("stage")) return "status";
  if (c.includes("note")) return "notes";
  return "__skip__";
}

export default function ImportPanel() {
  const fileRef = useRef();
  const [parsed, setParsed] = useState(null);
  const [mapping, setMapping] = useState({});
  const [summary, setSummary] = useState(null);
  const [busy, setBusy] = useState(false);

  const onFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setBusy(true); setSummary(null);
    try {
      const fd = new FormData(); fd.append("file", f);
      const { data } = await api.post("/import/parse", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setParsed(data);
      const m = {};
      data.columns.forEach((c) => { const g = guess(c); if (g !== "__skip__") m[g] = c; });
      setMapping(m);
      toast.success(`Read ${data.total} rows`);
    } catch (err) { toast.error(apiError(err)); } finally { setBusy(false); }
  };

  const commit = async () => {
    if (!mapping.name) return toast.error("Map the Lead Name column first");
    setBusy(true);
    try {
      const { data } = await api.post("/import/commit", { mapping, rows: parsed.rows });
      setSummary(data);
      toast.success(`${data.imported} imported, ${data.duplicates} duplicates skipped`);
    } catch (err) { toast.error(apiError(err)); } finally { setBusy(false); }
  };

  return (
    <Card className="p-6 space-y-4">
      <div className="flex items-center gap-2"><FileSpreadsheet size={18} className="text-primary" /><h3 className="font-bold text-slate-900">Tracker Import (CSV / Excel)</h3></div>
      <p className="text-sm text-slate-500">Upload your existing tracker, map the columns, and we'll import new records while skipping duplicates (matched by phone/email).</p>
      <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" onChange={onFile} className="hidden" data-testid="import-file-input" />
      <Button onClick={() => fileRef.current?.click()} disabled={busy} className="gap-2" data-testid="import-upload-btn"><Upload size={16} /> {busy ? "Working…" : "Choose file"}</Button>

      {parsed && (
        <div className="space-y-4">
          <div>
            <h4 className="font-semibold text-slate-800 mb-2">Map columns ({parsed.total} rows)</h4>
            <div className="grid sm:grid-cols-2 gap-3">
              {CRM_FIELDS.map(([field, label]) => (
                <div key={field} className="flex items-center gap-2">
                  <Label className="w-32 shrink-0">{label}</Label>
                  <Select value={mapping[field] || "__skip__"} onValueChange={(v) => setMapping((m) => ({ ...m, [field]: v === "__skip__" ? undefined : v }))}>
                    <SelectTrigger data-testid={`map-${field}`} className="h-8"><SelectValue placeholder="Skip" /></SelectTrigger>
                    <SelectContent><SelectItem value="__skip__">— Skip —</SelectItem>{parsed.columns.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              ))}
            </div>
          </div>

          <div className="overflow-x-auto scrollbar-thin border border-border rounded-lg">
            <table className="w-full text-xs">
              <thead className="bg-slate-50 text-slate-500"><tr>{parsed.columns.map((c) => <th key={c} className="px-2 py-1.5 text-left font-semibold whitespace-nowrap">{c}</th>)}</tr></thead>
              <tbody>{parsed.rows.slice(0, 5).map((r, i) => <tr key={i} className="border-t border-border">{parsed.columns.map((c) => <td key={c} className="px-2 py-1.5 whitespace-nowrap text-slate-600">{String(r[c] ?? "")}</td>)}</tr>)}</tbody>
            </table>
          </div>

          <Button onClick={commit} disabled={busy} data-testid="import-commit-btn" className="gap-2"><Upload size={16} /> Import Records</Button>
        </div>
      )}

      {summary && (
        <div data-testid="import-summary" className="rounded-lg border border-border p-4 bg-slate-50 text-sm">
          <p className="font-semibold text-slate-900 mb-2">Import summary</p>
          <div className="grid grid-cols-4 gap-3 text-center">
            <div><p className="text-xl font-extrabold text-slate-900">{summary.total}</p><p className="text-xs text-slate-500">Uploaded</p></div>
            <div><p className="text-xl font-extrabold text-emerald-600">{summary.imported}</p><p className="text-xs text-slate-500">New imported</p></div>
            <div><p className="text-xl font-extrabold text-amber-600">{summary.duplicates}</p><p className="text-xs text-slate-500">Duplicates</p></div>
            <div><p className="text-xl font-extrabold text-rose-600">{summary.invalid}</p><p className="text-xs text-slate-500">Need review</p></div>
          </div>
        </div>
      )}
    </Card>
  );
}
