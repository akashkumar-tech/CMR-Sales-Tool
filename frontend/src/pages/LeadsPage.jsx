import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useOptions } from "@/context/OptionsContext";
import { stageStyle, fmtDate, fmtDateTime, initials, localToday } from "@/lib/crm";
import { toast } from "sonner";
import LeadDrawer from "@/components/LeadDrawer";
import HandoverDialog from "@/components/HandoverDialog";
import { useAutoRefresh } from "@/lib/useAutoRefresh";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator } from "@/components/ui/dropdown-menu";
import { Search, MoreVertical } from "lucide-react";

export default function LeadsPage({ scope }) {
  const { isManager } = useAuth();
  const { labels, customFields } = useOptions();
  const [params, setParams] = useSearchParams();
  const [leads, setLeads] = useState([]);
  const [members, setMembers] = useState([]);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState(params.get("status") || "all");
  const [owner, setOwner] = useState(params.get("owner") || "all");
  const [source, setSource] = useState("all");
  const [team, setTeam] = useState("all");
  const [teams, setTeams] = useState([]);
  const [followUp, setFollowUp] = useState(params.get("follow_up") || "all");
  const [selected, setSelected] = useState(null);
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState("overview");
  const [handoverLead, setHandoverLead] = useState(null);
  const [handoverOpen, setHandoverOpen] = useState(false);
  const [savedFilters, setSavedFilters] = useState([]);
  const [showArchived, setShowArchived] = useState(false);
  const tableFields = customFields.filter((f) => f.show_in_table && !f.archived);

  const loadSaved = () => api.get("/saved-filters").then((r) => setSavedFilters(r.data)).catch(() => {});
  const applySaved = (f) => {
    const flt = f.filters || {};
    setStatus(flt.status || "all"); setOwner(flt.owner || "all"); setTeam(flt.team || "all"); setFollowUp(flt.follow_up || "all"); setSource(flt.source || "all");
  };
  const saveCurrentView = async () => {
    const name = window.prompt("Name this view (e.g. Hot Sales leads)");
    if (!name) return;
    const filters = {};
    if (status !== "all") filters.status = status;
    if (owner !== "all") filters.owner = owner;
    if (team !== "all") filters.team = team;
    if (source !== "all") filters.source = source;
    if (followUp !== "all") filters.follow_up = followUp;
    try { await api.post("/saved-filters", { name, filters }); toast.success("View saved"); loadSaved(); }
    catch (e) { toast.error(apiError(e)); }
  };
  const deleteSaved = async (id) => { try { await api.delete(`/saved-filters/${id}`); loadSaved(); } catch {} };

  const memberName = (id) => members.find((m) => m.id === id)?.name || "—";

  const load = useCallback(() => {
    const p = new URLSearchParams();
    if (scope === "mine") p.set("scope", "mine");
    if (search) p.set("search", search);
    if (status !== "all") p.set("status", status);
    if (owner !== "all") p.set("owner", owner);
    if (source !== "all") p.set("source", source);
    if (team !== "all") p.set("team", team);
    if (followUp !== "all") p.set("follow_up", followUp);
    if (showArchived) p.set("archived", "true");
    api.get(`/leads?${p.toString()}`).then((r) => setLeads(r.data)).catch(() => {});
  }, [scope, search, status, owner, source, team, followUp, showArchived]);

  useEffect(() => { api.get("/users").then((r) => setMembers(r.data)).catch(() => {}); api.get("/teams").then((r) => setTeams(r.data)).catch(() => {}); loadSaved(); }, []);
  useEffect(() => { load(); }, [load]);
  useAutoRefresh(load, 10000);
  useEffect(() => { setStatus(params.get("status") || "all"); setOwner(params.get("owner") || "all"); setFollowUp(params.get("follow_up") || "all"); }, [params]);

  const openLead = (id, t = "overview") => { setSelected(id); setTab(t); setOpen(true); };
  const overdue = (d) => d && d < localToday();

  const doAction = async (l, action) => {
    if (["view", "log", "demo", "history"].includes(action)) return openLead(l.id, action === "view" ? "overview" : action);
    if (action === "converted") { try { await api.patch(`/leads/${l.id}/stage`, { status: "Converted" }); toast.success("Marked converted"); load(); } catch (e) { toast.error(apiError(e)); } }
    if (action === "archive") { try { const r = await api.patch(`/leads/${l.id}/archive`); toast.success(r.data.archived ? "Archived" : "Unarchived"); load(); } catch (e) { toast.error(apiError(e)); } }
    if (action === "delete") { if (!window.confirm(`Delete ${l.name}?`)) return; try { await api.delete(`/leads/${l.id}`); toast.success("Deleted"); load(); } catch (e) { toast.error(apiError(e)); } }
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div><p className="text-[11px] font-bold uppercase tracking-[0.16em] text-primary">Prospects</p><h1 className="text-3xl font-extrabold tracking-tight text-slate-900">{scope === "mine" ? "My Leads" : "All Leads"}</h1></div>
        <span className="text-sm text-slate-500">{leads.length} records</span>
      </div>

      {scope === "all" && (
        <div className="flex flex-wrap items-center gap-2" data-testid="saved-filters-bar">
          <span className="text-xs font-semibold text-slate-400">Saved views:</span>
          {savedFilters.length === 0 && <span className="text-xs text-slate-400">none yet</span>}
          {savedFilters.map((f) => (
            <span key={f.id} className="inline-flex items-center gap-1 pl-3 pr-1.5 py-1 rounded-full text-xs font-medium border border-border bg-white text-slate-700">
              <button data-testid={`saved-filter-${f.id}`} onClick={() => applySaved(f)} className="hover:text-primary">{f.name}</button>
              <button data-testid={`delete-saved-${f.id}`} onClick={() => deleteSaved(f.id)} className="text-slate-300 hover:text-destructive">×</button>
            </span>
          ))}
          <button data-testid="save-view-btn" onClick={saveCurrentView} className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium border border-dashed border-primary/40 text-primary hover:bg-accent">+ Save current view</button>
        </div>
      )}

      <Card className="p-3 flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <Input data-testid="lead-search-input" placeholder="Search name, phone, email, IG, LinkedIn…" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <Select value={status} onValueChange={(v) => { setStatus(v); setParams((sp) => { v === "all" ? sp.delete("status") : sp.set("status", v); return sp; }); }}>
          <SelectTrigger data-testid="filter-status" className="w-40"><SelectValue placeholder="Status" /></SelectTrigger>
          <SelectContent><SelectItem value="all">All Statuses</SelectItem>{labels("stage").map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
        </Select>
        <Select value={followUp} onValueChange={(v) => { setFollowUp(v); setParams((sp) => { v === "all" ? sp.delete("follow_up") : sp.set("follow_up", v); return sp; }); }}>
          <SelectTrigger data-testid="filter-followup" className="w-36"><SelectValue placeholder="Follow-up" /></SelectTrigger>
          <SelectContent><SelectItem value="all">Any Follow-up</SelectItem><SelectItem value="overdue">Overdue</SelectItem><SelectItem value="today">Due Today</SelectItem><SelectItem value="upcoming">Upcoming</SelectItem></SelectContent>
        </Select>
        <Select value={source} onValueChange={setSource}>
          <SelectTrigger data-testid="filter-source" className="w-36"><SelectValue placeholder="Source" /></SelectTrigger>
          <SelectContent><SelectItem value="all">All Sources</SelectItem>{labels("source").map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
        </Select>
        {scope === "all" && (
          <Select value={owner} onValueChange={(v) => { setOwner(v); setParams((sp) => { v === "all" ? sp.delete("owner") : sp.set("owner", v); return sp; }); }}>
            <SelectTrigger data-testid="filter-owner" className="w-40"><SelectValue placeholder="Owner" /></SelectTrigger>
            <SelectContent><SelectItem value="all">All Owners</SelectItem>{members.filter((m) => m.role !== "admin").map((m) => <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>)}</SelectContent>
          </Select>
        )}
        {scope === "all" && teams.length > 0 && (
          <Select value={team} onValueChange={setTeam}>
            <SelectTrigger data-testid="filter-team" className="w-36"><SelectValue placeholder="Team" /></SelectTrigger>
            <SelectContent><SelectItem value="all">All Teams</SelectItem>{teams.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
          </Select>
        )}
        <label className="flex items-center gap-1.5 text-xs text-slate-600 cursor-pointer select-none" data-testid="show-archived-toggle">
          <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} /> Show archived
        </label>
      </Card>

      <Card className="overflow-hidden">
        <div className="overflow-x-auto scrollbar-thin">
          <table className="w-full text-sm whitespace-nowrap">
            <thead className="bg-slate-50 text-slate-500 text-left">
              <tr>
                <th className="px-4 py-3 font-semibold">Lead</th>
                <th className="px-4 py-3 font-semibold">Contact</th>
                <th className="px-4 py-3 font-semibold">Status</th>
                {scope === "all" && <th className="px-4 py-3 font-semibold">Owner</th>}
                <th className="px-4 py-3 font-semibold">Last Interaction</th>
                <th className="px-4 py-3 font-semibold text-center">Total</th>
                <th className="px-4 py-3 font-semibold">Next Follow-up</th>
                <th className="px-4 py-3 font-semibold">Demo</th>
                <th className="px-4 py-3 font-semibold">Payment</th>
                {tableFields.map((f) => <th key={f.id} className="px-4 py-3 font-semibold">{f.label}</th>)}
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {leads.map((l) => (
                <tr key={l.id} data-testid={`lead-row-${l.id}`} className="border-t border-border hover:bg-slate-50">
                  <td className="px-4 py-3 cursor-pointer" onClick={() => openLead(l.id)}><p className="font-semibold text-slate-900">{l.name}</p><p className="text-xs text-slate-500">{l.practice || "—"}</p></td>
                  <td className="px-4 py-3 text-slate-600">{l.phone || l.email || "—"}</td>
                  <td className="px-4 py-3"><span className={`px-2 py-0.5 rounded-full text-xs font-semibold border ${stageStyle(l.status)}`}>{l.status}</span>{l.lost_reason ? <span className="block text-[11px] text-rose-600 mt-0.5" data-testid={`lead-reason-${l.id}`}>{l.lost_reason}</span> : null}</td>
                  {scope === "all" && <td className="px-4 py-3"><span className="inline-flex items-center gap-1.5"><span className="h-6 w-6 rounded-full bg-primary/10 text-primary grid place-items-center text-[10px] font-bold">{initials(memberName(l.owner))}</span>{memberName(l.owner)}</span></td>}
                  <td className="px-4 py-3 text-slate-600 text-xs">{fmtDateTime(l.last_interaction_at)}{l.last_contacted_by_name ? <span className="block text-slate-400">by {l.last_contacted_by_name}</span> : null}</td>
                  <td className="px-4 py-3 text-center font-semibold text-slate-700">{l.total_interactions || 0}</td>
                  <td className={`px-4 py-3 text-xs ${overdue(l.next_follow_up) ? "text-rose-600 font-semibold" : "text-slate-600"}`}>{fmtDate(l.next_follow_up)}{overdue(l.next_follow_up) ? " ⚠" : ""}</td>
                  <td className="px-4 py-3 text-xs text-slate-600">{l.demo_status || "—"}</td>
                  <td className="px-4 py-3 text-xs text-slate-600">{l.payment_status || "—"}</td>
                  {tableFields.map((f) => <td key={f.id} className="px-4 py-3 text-xs text-slate-600">{Array.isArray(l.custom?.[f.key]) ? l.custom[f.key].join(", ") : (l.custom?.[f.key] === true ? "Yes" : (l.custom?.[f.key] || "—"))}</td>)}
                  <td className="px-4 py-3">
                    <DropdownMenu>
                      <DropdownMenuTrigger data-testid={`lead-menu-${l.id}`} className="text-slate-400 hover:text-slate-700"><MoreVertical size={18} /></DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="bg-white">
                        <DropdownMenuItem data-testid={`action-view-${l.id}`} onClick={() => doAction(l, "view")}>View / Edit</DropdownMenuItem>
                        <DropdownMenuItem onClick={() => doAction(l, "log")}>Log Interaction</DropdownMenuItem>
                        <DropdownMenuItem onClick={() => doAction(l, "demo")}>Book / Update Demo</DropdownMenuItem>
                        <DropdownMenuItem data-testid={`action-handover-${l.id}`} onClick={() => { setHandoverLead(l); setHandoverOpen(true); }}>Assign / Handover</DropdownMenuItem>
                        <DropdownMenuItem onClick={() => doAction(l, "converted")}>Mark Converted</DropdownMenuItem>
                        <DropdownMenuItem onClick={() => doAction(l, "history")}>View History</DropdownMenuItem>
                        <DropdownMenuItem data-testid={`action-archive-${l.id}`} onClick={() => doAction(l, "archive")}>{l.archived ? "Unarchive" : "Archive"}</DropdownMenuItem>
                        {isManager && <><DropdownMenuSeparator /><DropdownMenuItem className="text-destructive" onClick={() => doAction(l, "delete")}>Delete</DropdownMenuItem></>}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </td>
                </tr>
              ))}
              {leads.length === 0 && <tr><td colSpan={12} className="px-4 py-10 text-center text-slate-400">No leads found.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>

      <LeadDrawer leadId={selected} open={open} onOpenChange={setOpen} onChange={load} members={members} initialTab={tab} />
      {handoverLead && <HandoverDialog leadId={handoverLead.id} leadName={handoverLead.name} open={handoverOpen} onOpenChange={setHandoverOpen} members={members} onDone={load} />}
    </div>
  );
}
