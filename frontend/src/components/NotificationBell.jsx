import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAutoRefresh, relTime } from "@/lib/useAutoRefresh";
import { Bell, CheckCheck } from "lucide-react";
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent } from "@/components/ui/dropdown-menu";

export default function NotificationBell() {
  const navigate = useNavigate();
  const [count, setCount] = useState(0);
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);

  const loadCount = () => api.get("/notifications/unread-count").then((r) => setCount(r.data.count)).catch(() => {});
  const loadItems = () => api.get("/notifications").then((r) => setItems(r.data)).catch(() => {});

  useEffect(() => { loadCount(); }, []);
  useAutoRefresh(loadCount, 15000);
  useEffect(() => { if (open) loadItems(); }, [open]);

  const openItem = async (n) => {
    if (!n.read) { try { await api.post(`/notifications/${n.id}/read`); } catch {} loadCount(); }
    setOpen(false);
    if (n.link) navigate(n.link);
  };
  const readAll = async () => { try { await api.post("/notifications/read-all"); } catch {} loadCount(); loadItems(); };

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger data-testid="notification-bell" className="relative h-9 w-9 grid place-items-center rounded-lg hover:bg-slate-100 text-slate-600 transition-colors">
        <Bell size={18} />
        {count > 0 && (
          <span data-testid="notification-count" className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-primary text-primary-foreground text-[10px] font-bold grid place-items-center">
            {count > 9 ? "9+" : count}
          </span>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="bg-white w-80 p-0">
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-border">
          <span className="text-sm font-bold text-slate-900">Notifications</span>
          <button onClick={readAll} data-testid="mark-all-read-btn" className="text-xs text-primary hover:underline flex items-center gap-1"><CheckCheck size={13} /> Mark all read</button>
        </div>
        <div className="max-h-96 overflow-y-auto scrollbar-thin">
          {items.length === 0 && <p className="p-6 text-center text-sm text-slate-400">You're all caught up.</p>}
          {items.map((n) => (
            <button key={n.id} data-testid={`notification-${n.id}`} onClick={() => openItem(n)}
              className={`w-full text-left px-4 py-3 border-b border-border last:border-0 hover:bg-slate-50 transition-colors ${n.read ? "" : "bg-accent/40"}`}>
              <div className="flex items-start gap-2">
                {!n.read && <span className="mt-1.5 h-2 w-2 rounded-full bg-primary shrink-0" />}
                <div className={n.read ? "pl-4" : ""}>
                  <p className="text-sm font-semibold text-slate-800">{n.title}</p>
                  {n.body && <p className="text-xs text-slate-500">{n.body}</p>}
                  <p className="text-[11px] text-slate-400 mt-0.5">{relTime(n.created_at)}</p>
                </div>
              </div>
            </button>
          ))}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
