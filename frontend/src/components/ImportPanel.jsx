import { useRef, useState } from "react";
import { api, apiError } from "@/lib/api";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Upload, FileSpreadsheet } from "lucide-react";

const CRM_FIELDS = [
  ["name", "Lead Name"], ["phone", "Phone / Contact"], ["email", "Email"], ["status", "Status"],
  ["owner", "Owner"], ["last_interaction_at", "Last Interaction"], ["total_interactions", "Total Interactions"],
  ["next_follow_up", "Next Follow-up"], ["demo_status", "Demo"], ["payment_status", "Payment"],
  ["notes", "Notes"], ["practice", "Practice / Clinic"], ["location", "Location"],
  ["source", "Source"], ["instagram", "Instagram"], ["linkedin", "LinkedIn"],
];

const normHeader = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

const HEADER_ALIASES = {
  name: ["lead", "lead name", "name", "client", "customer"],
  phone: ["phone", "contact", "mobile", "whatsapp", "phone number", "contact no", "contact number", "cell", "tel"],
  email: ["email", "e mail", "email address"],
  status: ["status", "stage", "lead status"],
  owner: ["owner", "lead owner", "assigned to", "assignee", "rep", "agent"],
  last_interaction_at: ["last interaction", "last contact", "last contacted", "last interaction at", "last touch"],
  total_interactions: ["total", "total interactions", "touches", "interaction count"],
  next_follow_up: ["next follow up", "next follow-up", "next contact", "follow up", "follow-up", "followup", "next followup"],
  demo_status: ["demo", "demo status"],
  payment_status: ["payment", "payment status"],
  notes: ["notes", "note", "remarks", "comments"],
  practice: ["practice", "clinic", "hospital", "practice clinic", "company", "organization"],
  location: ["location", "city", "address", "area", "state"],
  source: ["source", "lead source", "channel"],
  instagram: ["instagram", "ig", "insta"],
  linkedin: ["linkedin", "li"],
};

// Checked in order: specific fields come before "name" so headers like "Clinic Name" or
// "Instagram Username" aren't taken as the lead's name.
const FIELD_RULES = [
  ["email", /e ?mail/],
  ["phone", /phone|mobile|whats ?app|\bcontact\b(?!\s*person)|\bcell\b|\bmob\b|\btel\b/],
  ["instagram", /insta|\big\b/],
  ["linkedin", /linked ?in/],
  ["practice", /practice|clinic|hospital|company|organi[sz]ation|business/],
  ["location", /location|city|address|\barea\b|\bstate\b|region|country/],
  ["source", /source|channel/],
  ["status", /status|stage/],
  ["owner", /owner|assigned|assignee|\brep\b|agent/],
  ["last_interaction_at", /last (interaction|contact)|interaction/],
  ["total_interactions", /\btotal\b|interaction count|touches/],
  ["next_follow_up", /next (follow|contact)|follow ?up|followup/],
  ["demo_status", /\bdemo\b/],
  ["payment_status", /\bpayment\b|paid/],
  ["notes", /note|remark|comment/],
  ["name", /name|\blead\b|doctor|\bdr\b|client|customer|contact person/],
];

function guessMapping(columns) {
  const m = {};
  const used = new Set();
  const take = (field, col) => { if (!m[field] && !used.has(col)) { m[field] = col; used.add(col); } };
  // Exact & alias header matches ("Name", "Lead Name", "Contact", "Phone") win over regex rules.
  columns.forEach((col) => {
    const h = normHeader(col);
    for (const [field, aliases] of Object.entries(HEADER_ALIASES)) {
      if (aliases.includes(h) || h === field) {
        take(field, col);
        break;
      }
    }
  });
  columns.forEach((col) => {
    const h = normHeader(col);
    if (!h || h.startsWith("unnamed")) return;
    const rule = FIELD_RULES.find(([, re]) => re.test(h));
    if (rule) take(rule[0], col);
  });
  return m;
}

export default function ImportPanel() {
  const fileRef = useRef();
  const [parsed, setParsed] = useState(null);
  const [mapping, setMapping] = useState({});
  const [summary, setSummary] = useState(null);
  const [busy, setBusy] = useState(false);
  // Every row the backend did not insert, with its sheet row number and reason.
  const skippedRows = (summary?.details || []).filter((d) => d.status !== "imported");

  const onFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setBusy(true); setSummary(null);
    try {
      const fd = new FormData(); fd.append("file", f);
      const { data } = await api.post("/import/parse", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setParsed(data);
      setMapping(guessMapping(data.columns));
      if (data.over_limit) toast.warning(`Only the first ${data.total} rows can be imported at once — ${data.over_limit} more rows were not read. Split the file to import them.`);
      else toast.success(`Read ${data.total} rows`);
    } catch (err) { toast.error(apiError(err)); } finally { setBusy(false); }
  };

  const commit = async () => {
    if (!mapping.name) return toast.error("Map the Lead Name column first");
    setBusy(true);
    try {
      const { data } = await api.post("/import/commit", { mapping, rows: parsed.rows });
      setSummary(data);
      const skipped = data.duplicates + data.missing_name + data.invalid;
      toast.success(`${data.imported} imported${skipped ? `, ${skipped} skipped` : ""}`);
    } catch (err) { toast.error(apiError(err)); } finally { setBusy(false); }
  };

  return (
    <Card className="p-6 space-y-4">
      <div className="flex items-center gap-2"><FileSpreadsheet size={18} className="text-primary" /><h3 className="font-bold text-slate-900">Tracker Import (CSV / Excel)</h3></div>
      <p className="text-sm text-slate-500">Upload your existing tracker, map the columns, and we'll import new records while skipping duplicates (a row is a duplicate only when every column matches a row that was already imported). The Owner column decides who owns each lead; rows whose owner isn't a team member are listed for review.</p>
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
          <div className="grid grid-cols-5 gap-3 text-center">
            <div><p className="text-xl font-extrabold text-slate-900">{summary.total}</p><p className="text-xs text-slate-500">Uploaded</p></div>
            <div><p data-testid="import-imported" className="text-xl font-extrabold text-emerald-600">{summary.imported}</p><p className="text-xs text-slate-500">Imported</p></div>
            <div><p data-testid="import-duplicates" className="text-xl font-extrabold text-amber-600">{summary.duplicates}</p><p className="text-xs text-slate-500">Duplicates</p></div>
            <div><p data-testid="import-missing-name" className="text-xl font-extrabold text-rose-600">{summary.missing_name}</p><p className="text-xs text-slate-500">Name missing</p></div>
            <div><p data-testid="import-invalid" className="text-xl font-extrabold text-rose-600">{summary.invalid}</p><p className="text-xs text-slate-500">Other issues</p></div>
          </div>
          {skippedRows.length > 0 && (
            <div className="mt-3">
              <p className="text-xs font-semibold text-slate-700 mb-1">Skipped rows ({skippedRows.length}) — not imported</p>
              <div className="max-h-56 overflow-y-auto scrollbar-thin border border-border rounded-md bg-white">
                <table data-testid="import-skipped-table" className="w-full text-xs">
                  <thead className="bg-slate-50 text-slate-500 sticky top-0"><tr><th className="px-2 py-1 text-left font-semibold">Row</th><th className="px-2 py-1 text-left font-semibold">Name</th><th className="px-2 py-1 text-left font-semibold">Reason</th></tr></thead>
                  <tbody>{skippedRows.map((d) => (
                    <tr key={d.row} className="border-t border-border">
                      <td className="px-2 py-1 text-slate-600">{d.row}</td>
                      <td className="px-2 py-1 text-slate-600">{d.name}</td>
                      <td className={`px-2 py-1 ${d.status === "duplicate" ? "text-amber-700" : "text-rose-700"}`}>{d.reason}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
