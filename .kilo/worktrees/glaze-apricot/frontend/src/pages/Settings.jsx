import { useEffect, useState } from "react";
import { api, apiError, API } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useOptions } from "@/context/OptionsContext";
import { fmtDateTime, initials } from "@/lib/crm";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Download, Plus, Archive, ArchiveRestore, Power, Mail, Pencil, Users } from "lucide-react";
import CustomFieldsPanel from "@/components/CustomFieldsPanel";
import ImportPanel from "@/components/ImportPanel";

const OPTION_TYPES = [
  ["stage", "Pipeline Stages / Statuses"], ["source", "Lead Sources"], ["contact_method", "Contact Methods"],
  ["activity_type", "Activity Types"], ["lost_reason", "Lost / Closed Reasons"], ["demo_status", "Demo Statuses"],
  ["followup_type", "Follow-up Types"], ["invoice_status", "Invoice Statuses"], ["payment_status", "Payment Statuses"],
];

export default function Settings() {
  const { user: me, isManager, isAdmin } = useAuth();
  const { refresh: refreshContext } = useOptions();
  // Settings lists archived options too (dimmed, with restore); the rest of the app uses the context (active only).
  const [options, setOptions] = useState({});
  const refresh = () => { refreshContext(); api.get("/options?include_archived=true").then((r) => setOptions(r.data)).catch(() => {}); };
  // Managers manage staff below them; admin/manager accounts are admin-only. Nobody deactivates themselves.
  const canManage = (u) => isAdmin || !["admin", "manager"].includes(u.role) || u.id === me?.id;
  const [users, setUsers] = useState([]);
  const [audit, setAudit] = useState([]);
  const [openUser, setOpenUser] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const emptyUser = { name: "", email: "", role: "employee", employee_id: "", team: "", manager_id: "", joining_date: "", employment_type: "Full-time" };
  const [form, setForm] = useState(emptyUser);
  const [newOption, setNewOption] = useState({});
  const managers = users.filter((u) => u.role === "manager" || u.role === "admin");
  const managerName = (id) => users.find((u) => u.id === id)?.name || "—";

  const loadUsers = () => api.get("/users").then((r) => setUsers(r.data));
  useEffect(() => {
    loadUsers();
    if (isManager) api.get("/audit").then((r) => setAudit(r.data.slice(0, 40))).catch(() => {});
    api.get("/options?include_archived=true").then((r) => setOptions(r.data)).catch(() => {});
  }, [isManager]);

  const openAdd = () => { setEditingId(null); setForm(emptyUser); setOpenUser(true); };
  const openEdit = (u) => { setEditingId(u.id); setForm({ name: u.name || "", email: u.email || "", role: u.role, employee_id: u.employee_id || "", team: u.team || "", manager_id: u.manager_id || "", joining_date: (u.joining_date || "").slice(0, 10), employment_type: u.employment_type || "Full-time" }); setOpenUser(true); };

  const saveUser = async () => {
    if (!form.name || !form.email) return toast.error("Name and email required");
    try {
      if (editingId) {
        await api.patch(`/users/${editingId}`, { name: form.name, role: form.role, team: form.team, manager_id: form.manager_id || null, joining_date: form.joining_date || null, employment_type: form.employment_type });
        toast.success("Team member updated");
      } else {
        await api.post("/users", form);
        toast.success("Team member added — they can now sign in with OTP");
      }
      setOpenUser(false); setForm(emptyUser); setEditingId(null); loadUsers();
    } catch (e) { toast.error(apiError(e)); }
  };
  const toggleActive = async (u) => {
    try { await api.patch(`/users/${u.id}`, { active: !u.active }); toast.success(u.active ? "Deactivated" : "Reactivated"); loadUsers(); }
    catch (e) { toast.error(apiError(e)); }
  };
  const [reassign, setReassign] = useState(null);
  const [reassignCount, setReassignCount] = useState(null);
  const [reassignTo, setReassignTo] = useState("");
  const openReassign = async (u) => {
    setReassign(u); setReassignCount(null); setReassignTo("");
    try { const { data } = await api.get(`/reassign-preview?from_user=${u.id}`); setReassignCount(data.open_count); }
    catch { setReassignCount(null); }
  };
  const doBulkReassign = async (toUser) => {
    try {
      const { data } = await api.post("/leads/bulk-reassign", { from_user: reassign.id, to_user: toUser });
      toast.success(`Moved ${data.reassigned} open lead(s)`); setReassign(null);
    } catch (e) { toast.error(apiError(e)); }
  };

  const addOption = async (type) => {
    const label = (newOption[type] || "").trim();
    if (!label) return;
    try { await api.post("/options", { type, label }); setNewOption((n) => ({ ...n, [type]: "" })); refresh(); toast.success("Option added"); }
    catch (e) { toast.error(apiError(e)); }
  };
  const patchOption = async (o, updates) => {
    try { await api.patch(`/options/${o.id}`, updates); refresh(); }
    catch (e) { toast.error(apiError(e)); }
  };
  const renameOption = async (o) => {
    const label = window.prompt("Rename option", o.label);
    if (label && label !== o.label) patchOption(o, { label });
  };

  const exportCsv = async () => {
    try {
      const res = await fetch(`${API}/export/leads.csv`, { headers: { Authorization: `Bearer ${localStorage.getItem("beet_token")}` } });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        toast.error(typeof body.detail === "string" ? `Export failed: ${body.detail}` : "Export failed"); return;
      }
      const blob = await res.blob(); const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = "beet_leads.csv"; a.click();
      toast.success("CSV exported");
    } catch { toast.error("Export failed"); }
  };

  return (
    <div className="space-y-6">
      <div><p className="text-[11px] font-bold uppercase tracking-[0.16em] text-primary">Admin</p><h1 className="text-3xl font-extrabold tracking-tight text-slate-900">Settings</h1></div>

      <Tabs defaultValue="config">
        <TabsList>
          <TabsTrigger value="config" data-testid="settings-tab-config">CRM Configuration</TabsTrigger>
          <TabsTrigger value="custom" data-testid="settings-tab-custom">Custom Fields</TabsTrigger>
          <TabsTrigger value="import" data-testid="settings-tab-import">Import</TabsTrigger>
          <TabsTrigger value="team" data-testid="settings-tab-team">Team Members</TabsTrigger>
          <TabsTrigger value="data" data-testid="settings-tab-data">Data & Audit</TabsTrigger>
        </TabsList>

        <TabsContent value="config" className="mt-4">
          {!isManager && <Card className="p-6 text-sm text-slate-500">Only managers/admins can edit configuration.</Card>}
          {isManager && (
            <div className="grid md:grid-cols-2 gap-4">
              {OPTION_TYPES.map(([type, title]) => (
                <Card key={type} className="p-5" data-testid={`config-${type}`}>
                  <h3 className="font-bold text-slate-900 mb-3">{title}</h3>
                  <div className="space-y-1.5 mb-3">
                    {(options[type] || []).map((o) => (
                      <div key={o.id} className={`flex items-center justify-between text-sm px-2 py-1.5 rounded-lg ${o.archived ? "opacity-40 bg-slate-50" : "bg-slate-50"}`}>
                        <span className="text-slate-800">{o.label}{o.requires_reason ? <span className="ml-2 text-[10px] text-amber-600">needs reason</span> : ""}</span>
                        <div className="flex items-center gap-1">
                          <button onClick={() => renameOption(o)} className="text-xs text-primary hover:underline px-1">Rename</button>
                          <button data-testid={`archive-option-${o.id}`} onClick={() => patchOption(o, { archived: !o.archived })} className="text-slate-400 hover:text-slate-700">{o.archived ? <ArchiveRestore size={14} /> : <Archive size={14} />}</button>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <Input data-testid={`new-option-${type}`} placeholder="Add option…" value={newOption[type] || ""} onChange={(e) => setNewOption((n) => ({ ...n, [type]: e.target.value }))} onKeyDown={(e) => e.key === "Enter" && addOption(type)} className="h-8" />
                    <Button size="sm" data-testid={`add-option-${type}`} onClick={() => addOption(type)} className="h-8"><Plus size={14} /></Button>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="custom" className="mt-4"><CustomFieldsPanel /></TabsContent>
        <TabsContent value="import" className="mt-4">{isManager ? <ImportPanel /> : <Card className="p-6 text-sm text-slate-500">Only managers/admins can import.</Card>}</TabsContent>

        <TabsContent value="team" className="mt-4">
          <Card className="p-6">
            <div className="flex items-center justify-between mb-1">
              <h3 className="font-bold text-slate-900">Team Members ({users.length})</h3>
              {isManager && <Button size="sm" data-testid="add-employee-btn" onClick={openAdd} className="gap-1"><Plus size={14} /> Add Member</Button>}
            </div>
            <p className="text-xs text-slate-500 mb-4">Add staff here — once activated they sign in themselves with their Beet.Health email + OTP. Deactivate leavers to keep their history.</p>
            <div className="space-y-2">
              {users.map((u) => (
                <div key={u.id} data-testid={`user-row-${u.id}`} className={`flex items-center gap-3 p-2.5 rounded-lg bg-slate-50 ${u.active === false ? "opacity-60" : ""}`}>
                  <div className="h-9 w-9 rounded-full bg-primary/10 text-primary grid place-items-center text-sm font-bold">{initials(u.name)}</div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-slate-900">{u.name} <span className="text-xs font-normal text-slate-400">{u.employee_id || ""}</span>{u.active === false && <span className="ml-2 text-xs text-rose-600">Inactive</span>}</p>
                    <p className="text-xs text-slate-500 truncate">{u.email} · {u.team || "no team"} · mgr: {u.manager_id ? managerName(u.manager_id) : "—"}{u.employment_type ? ` · ${u.employment_type}` : ""}</p>
                  </div>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-slate-200 text-slate-600 capitalize">{u.role}</span>
                  {isManager && canManage(u) && <button data-testid={`edit-user-${u.id}`} onClick={() => openEdit(u)} className="p-1.5 rounded-lg text-slate-400 hover:text-primary"><Pencil size={15} /></button>}
                  {isManager && u.role !== "admin" && <button data-testid={`reassign-user-${u.id}`} onClick={() => openReassign(u)} className="p-1.5 rounded-lg text-slate-400 hover:text-primary" title="Reassign this person's open leads"><Users size={15} /></button>}
                  {isManager && canManage(u) && u.id !== me?.id && <button data-testid={`toggle-active-${u.id}`} onClick={() => toggleActive(u)} className={`p-1.5 rounded-lg ${u.active === false ? "text-emerald-600" : "text-slate-400 hover:text-destructive"}`}><Power size={16} /></button>}
                </div>
              ))}
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="data" className="mt-4 grid lg:grid-cols-2 gap-6">
          {isManager && (
            <Card className="p-6">
              <h3 className="font-bold text-slate-900 mb-1">Data Export</h3>
              <p className="text-sm text-slate-500 mb-4">Download all CRM leads as a CSV file.</p>
              <Button data-testid="export-csv-btn" onClick={exportCsv} className="gap-2"><Download size={16} /> Export CRM Data (CSV)</Button>
            </Card>
          )}
          {isManager && (
            <Card className="p-6">
              <h3 className="font-bold text-slate-900 mb-1">Follow-up Reminders</h3>
              <p className="text-sm text-slate-500 mb-4">Each team member is automatically emailed their due & overdue follow-ups every morning (08:00, team time zone). Send them now:</p>
              <Button data-testid="send-reminders-btn" variant="outline" className="gap-2" onClick={async () => { try { const { data } = await api.post("/reminders/run"); toast.success(`Reminders sent to ${data.sent.length} team member(s)`); } catch (e) { toast.error(apiError(e)); } }}><Mail size={16} /> Send Reminders Now</Button>
            </Card>
          )}
          {isManager && (
            <Card className="p-6">
              <h3 className="font-bold text-slate-900 mb-3">Audit Log</h3>
              <div className="space-y-1.5 max-h-80 overflow-y-auto scrollbar-thin">
                {audit.map((a) => (
                  <div key={a.id} className="text-xs text-slate-600 border-b border-border pb-1">
                    <b className="text-slate-800">{a.actor_name}</b> {a.action} {a.entity} {a.field}{a.prev || a.new ? `: ${a.prev || "—"} → ${a.new}` : ""} <span className="text-slate-400">· {a.detail}</span>
                    <span className="text-slate-400 float-right">{fmtDateTime(a.timestamp)}</span>
                  </div>
                ))}
                {audit.length === 0 && <p className="text-sm text-slate-400">No history yet.</p>}
              </div>
            </Card>
          )}
        </TabsContent>
      </Tabs>

      {reassign && (
        <Dialog open={!!reassign} onOpenChange={() => setReassign(null)}>
          <DialogContent className="bg-white">
            <DialogHeader><DialogTitle>Reassign {reassign.name}'s open leads</DialogTitle></DialogHeader>
            <p className="text-sm text-slate-500">Move all of {reassign.name}'s open (non-closed) leads to another owner. Closed/converted/lost leads stay for historical accuracy.</p>
            <div data-testid="reassign-preview-count" className="rounded-lg bg-accent text-accent-foreground text-sm font-semibold px-3 py-2">
              {reassignCount === null ? "Counting open leads…" : `${reassignCount} open lead${reassignCount === 1 ? "" : "s"} will move`}
            </div>
            <div className="space-y-2 pt-2">
              <Label>New owner</Label>
              <Select value={reassignTo} onValueChange={setReassignTo}>
                <SelectTrigger data-testid="reassign-target-select"><SelectValue placeholder="Choose team member" /></SelectTrigger>
                <SelectContent>{users.filter((u) => u.role !== "admin" && u.id !== reassign.id && u.active !== false).map((u) => <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setReassign(null)}>Cancel</Button>
              <Button data-testid="reassign-confirm-btn" disabled={!reassignTo} onClick={() => doBulkReassign(reassignTo)}>Move leads</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      <Dialog open={openUser} onOpenChange={setOpenUser}>
        <DialogContent className="bg-white max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editingId ? "Edit Team Member" : "Add Team Member"}</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2"><Label>Full Name *</Label><Input data-testid="emp-name-input" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} /></div>
            <div><Label>Employee ID</Label><Input data-testid="emp-id-input" value={form.employee_id} disabled={!!editingId} onChange={(e) => setForm((f) => ({ ...f, employee_id: e.target.value }))} placeholder="e.g. BH-104" /></div>
            <div><Label>Beet Work Email *</Label><Input data-testid="emp-email-input" type="email" value={form.email} disabled={!!editingId} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} placeholder="name@beet.health" /></div>
            <div><Label>Role</Label>
              <Select value={form.role} onValueChange={(v) => setForm((f) => ({ ...f, role: v }))}>
                <SelectTrigger data-testid="emp-role-select"><SelectValue /></SelectTrigger>
                <SelectContent>{(isAdmin ? ["admin", "manager", "employee", "intern"] : ["manager", "employee", "intern"]).map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div><Label>Manager</Label>
              <Select value={form.manager_id || "none"} onValueChange={(v) => setForm((f) => ({ ...f, manager_id: v === "none" ? "" : v }))}>
                <SelectTrigger data-testid="emp-manager-select"><SelectValue placeholder="—" /></SelectTrigger>
                <SelectContent><SelectItem value="none">— None —</SelectItem>{managers.map((m) => <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div><Label>Team</Label><Input data-testid="emp-team-input" value={form.team} onChange={(e) => setForm((f) => ({ ...f, team: e.target.value }))} placeholder="e.g. Sales" /></div>
            <div><Label>Joining Date</Label><Input type="date" data-testid="emp-joining-input" value={form.joining_date} onChange={(e) => setForm((f) => ({ ...f, joining_date: e.target.value }))} /></div>
            <div><Label>Employment Type</Label>
              <Select value={form.employment_type} onValueChange={(v) => setForm((f) => ({ ...f, employment_type: v }))}>
                <SelectTrigger data-testid="emp-type-select"><SelectValue /></SelectTrigger>
                <SelectContent>{["Full-time", "Part-time", "Intern", "Contract"].map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setOpenUser(false)}>Cancel</Button><Button data-testid="save-employee-btn" onClick={saveUser}>{editingId ? "Save" : "Add & Approve"}</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
