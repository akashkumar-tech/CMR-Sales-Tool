export const STAGE_STYLES = {
  "New Lead": "bg-slate-100 text-slate-700 border-slate-300",
  "Contacted": "bg-sky-50 text-sky-700 border-sky-200",
  "Replied": "bg-blue-50 text-blue-700 border-blue-200",
  "Interested": "bg-amber-50 text-amber-700 border-amber-200",
  "Demo Booked": "bg-purple-50 text-purple-700 border-purple-200",
  "Demo Completed": "bg-indigo-50 text-indigo-700 border-indigo-200",
  "Demo No-show": "bg-rose-50 text-rose-700 border-rose-200",
  "Rescheduled": "bg-fuchsia-50 text-fuchsia-700 border-fuchsia-200",
  "Trial": "bg-teal-50 text-teal-700 border-teal-200",
  "Pricing Shared": "bg-violet-50 text-violet-700 border-violet-200",
  "Follow-up": "bg-orange-50 text-orange-700 border-orange-200",
  "Invoice Raised": "bg-cyan-50 text-cyan-700 border-cyan-200",
  "Payment Pending": "bg-yellow-50 text-yellow-700 border-yellow-200",
  "Paid": "bg-emerald-50 text-emerald-700 border-emerald-200",
  "Not Paid": "bg-red-50 text-red-700 border-red-200",
  "Converted": "bg-emerald-100 text-emerald-800 border-emerald-300",
  "Not Interested": "bg-rose-50 text-rose-700 border-rose-200",
  "Lost": "bg-rose-100 text-rose-800 border-rose-300",
  "Closed": "bg-zinc-200 text-zinc-700 border-zinc-400",
  "No Response": "bg-zinc-100 text-zinc-600 border-zinc-300",
};

export function stageStyle(s) {
  return STAGE_STYLES[s] || "bg-slate-100 text-slate-700 border-slate-300";
}

export function fmtDate(d) {
  if (!d) return "—";
  try { return new Date(d).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }); }
  catch { return d; }
}
export function fmtDateTime(d) {
  if (!d) return "—";
  try { return new Date(d).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }); }
  catch { return d; }
}
// Today's date (YYYY-MM-DD) in the user's local time zone — due dates are local calendar dates.
export function localToday() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
export function initials(name) {
  return (name || "?").split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();
}
