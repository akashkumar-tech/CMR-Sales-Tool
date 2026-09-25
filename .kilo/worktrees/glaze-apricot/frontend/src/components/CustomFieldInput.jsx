import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export default function CustomFieldInput({ field, value, onChange, className = "" }) {
  const t = field.type;
  const set = (v) => onChange(field.key, v);
  const testid = `custom-field-${field.key}`;

  let control;
  if (t === "longtext") {
    control = <Textarea data-testid={testid} value={value || ""} onChange={(e) => set(e.target.value)} />;
  } else if (t === "dropdown") {
    control = (
      <Select value={value || ""} onValueChange={set}>
        <SelectTrigger data-testid={testid}><SelectValue placeholder="—" /></SelectTrigger>
        <SelectContent>{(field.options || []).map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}</SelectContent>
      </Select>
    );
  } else if (t === "checkbox") {
    control = <div className="flex items-center gap-2 pt-1"><Checkbox data-testid={testid} checked={!!value} onCheckedChange={set} /><span className="text-sm text-slate-600">Yes</span></div>;
  } else if (t === "multiselect") {
    const arr = Array.isArray(value) ? value : [];
    control = (
      <div className="flex flex-wrap gap-2 pt-1" data-testid={testid}>
        {(field.options || []).map((o) => {
          const on = arr.includes(o);
          return <button type="button" key={o} onClick={() => set(on ? arr.filter((x) => x !== o) : [...arr, o])}
            className={`px-2.5 py-1 rounded-full text-xs font-medium border ${on ? "bg-primary text-white border-primary" : "border-border text-slate-600"}`}>{o}</button>;
        })}
      </div>
    );
  } else {
    const inputType = t === "number" ? "number" : t === "date" ? "date" : t === "datetime" ? "datetime-local" : "text";
    control = <Input data-testid={testid} type={inputType} value={value || ""} onChange={(e) => set(e.target.value)} />;
  }

  return <div className={className}><Label>{field.label}{field.required ? " *" : ""}</Label>{control}</div>;
}
