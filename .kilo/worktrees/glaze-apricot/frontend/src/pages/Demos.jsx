import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { stageStyle, fmtDate } from "@/lib/crm";
import { useAutoRefresh } from "@/lib/useAutoRefresh";
import LeadDrawer from "@/components/LeadDrawer";
import { Card } from "@/components/ui/card";
import { Calendar, User, Clock } from "lucide-react";

export default function Demos() {
  const [leads, setLeads] = useState([]);
  const [members, setMembers] = useState([]);
  const [selected, setSelected] = useState(null);
  const [open, setOpen] = useState(false);

  const load = () => api.get("/leads").then((r) => setLeads(r.data.filter((l) => l.demo_date || ["Demo Booked", "Demo Completed"].includes(l.status)))).catch(() => {});
  useEffect(() => { load(); api.get("/users").then((r) => setMembers(r.data)).catch(() => {}); }, []);
  useAutoRefresh(load, 10000);
  const memberName = (id) => members.find((m) => m.id === id)?.name || "Unassigned";

  return (
    <div className="space-y-5">
      <div><p className="text-[11px] font-bold uppercase tracking-[0.16em] text-primary">Demos</p><h1 className="text-3xl font-extrabold tracking-tight text-slate-900">Demo Pipeline</h1></div>
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
        {leads.map((l) => (
          <Card key={l.id} data-testid={`demo-card-${l.id}`} onClick={() => { setSelected(l.id); setOpen(true); }} className="p-5 cursor-pointer hover:-translate-y-0.5 transition-transform">
            <div className="flex items-center justify-between">
              <span className={`px-2 py-0.5 rounded-full text-xs font-semibold border ${stageStyle(l.status)}`}>{l.status}</span>
              <span className="text-xs px-2 py-0.5 rounded-full bg-purple-50 text-purple-700 border border-purple-100">{l.demo_status || "Scheduled"}</span>
            </div>
            <p className="font-bold text-slate-900 mt-3">{l.name}</p>
            <p className="text-sm text-slate-500">{l.practice}</p>
            <div className="mt-3 space-y-1 text-xs text-slate-500">
              <p className="flex items-center gap-1.5"><Calendar size={13} /> {fmtDate(l.demo_date)}{l.demo_time ? <span className="inline-flex items-center gap-1 ml-1"><Clock size={12} /> {l.demo_time}</span> : null}</p>
              <p className="flex items-center gap-1.5"><User size={13} /> {memberName(l.demo_owner)}</p>
            </div>
          </Card>
        ))}
        {leads.length === 0 && <p className="text-sm text-slate-400 col-span-full text-center py-8">No demos scheduled.</p>}
      </div>
      <LeadDrawer leadId={selected} open={open} onOpenChange={setOpen} onChange={load} members={members} initialTab="demo" />
    </div>
  );
}
