import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { apiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ArrowLeft } from "lucide-react";

export default function Login() {
  const { requestOtp, verifyOtp } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState("email");
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [busy, setBusy] = useState(false);
  const [devOtp, setDevOtp] = useState("");

  // Set by the API client when a session ends mid-use (expired, revoked or deactivated).
  const [expired] = useState(() => !!new URLSearchParams(window.location.search).get("expired"));

  const sendOtp = async (e) => {
    e?.preventDefault();
    if (!email) return;
    setBusy(true);
    try {
      const res = await requestOtp(email.trim());
      setStep("otp");
      if (res.dev_otp) { setDevOtp(res.dev_otp); toast.info(`Dev OTP: ${res.dev_otp}`); }
      else toast.success("Code sent to your email");
    } catch (err) { toast.error(apiError(err)); } finally { setBusy(false); }
  };

  const verify = async (e) => {
    e?.preventDefault();
    setBusy(true);
    try { await verifyOtp(email.trim(), otp.trim()); toast.success("Welcome to Beet.Health"); navigate("/dashboard"); }
    catch (err) { toast.error(apiError(err)); } finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-background">
      <div className="hidden lg:flex flex-col justify-between p-12 text-white" style={{ background: "linear-gradient(150deg,#4F46E5,#0D9488)" }}>
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center rounded-xl bg-white px-3 py-2 shadow-sm"><img src="/beet-health-logo.png" alt="Beet.Health" className="h-8 w-auto" /></span>
          <span className="font-extrabold text-xl">CRM</span>
        </div>
        <div>
          <h1 className="text-4xl font-extrabold tracking-tight leading-tight">Your team's sales pipeline, coordinated and secure.</h1>
          <p className="mt-4 text-white/80 text-base">Approved team members sign in with a one-time code. Track leads, activities, demos, follow-ups and conversions — with private ownership and a real-time manager overview.</p>
        </div>
        <p className="text-white/60 text-sm">Secure email + OTP login · Configurable pipeline</p>
      </div>
      <div className="flex items-center justify-center p-6">
        {step === "email" ? (
          <form onSubmit={sendOtp} className="w-full max-w-sm space-y-5">
            <div><h2 className="text-2xl font-bold text-slate-900">Sign in</h2><p className="text-sm text-slate-500">Enter your approved Beet.Health work email</p></div>
            {expired && <div data-testid="session-expired-note" className="text-xs bg-amber-50 border border-amber-200 text-amber-800 rounded-lg p-2">Your session ended. Please sign in again.</div>}
            <div><Label>Work Email</Label><Input data-testid="login-email-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@beet.health" required /></div>
            <Button data-testid="send-otp-btn" type="submit" className="w-full" disabled={busy}>{busy ? "Sending…" : "Send login code"}</Button>
            <div className="pt-2">
              <p className="text-xs text-slate-400 mb-2">Only approved staff can sign in. Initial admin:</p>
              <div className="flex flex-wrap gap-2">
                <button type="button" data-testid="quick-email-admin" onClick={() => setEmail("admin@beet.health")} className="px-2.5 py-1 rounded-full text-xs font-medium border border-border text-slate-600 hover:bg-slate-50">admin@beet.health</button>
                <button type="button" data-testid="quick-email-manager" onClick={() => setEmail("paripsa.tripathi@beet.health")} className="px-2.5 py-1 rounded-full text-xs font-medium border border-border text-slate-600 hover:bg-slate-50">paripsa.tripathi@beet.health</button>
              </div>
            </div>
          </form>
        ) : (
          <form onSubmit={verify} className="w-full max-w-sm space-y-5">
            <button type="button" onClick={() => { setStep("email"); setOtp(""); }} className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"><ArrowLeft size={14} /> Back</button>
            <div><h2 className="text-2xl font-bold text-slate-900">Enter code</h2><p className="text-sm text-slate-500">We sent a 6-digit code to <b>{email}</b></p></div>
            {devOtp && <div className="text-xs bg-amber-50 border border-amber-200 text-amber-800 rounded-lg p-2">Dev mode code: <b>{devOtp}</b></div>}
            <div><Label>One-time code</Label><Input data-testid="otp-input" inputMode="numeric" maxLength={6} value={otp} onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))} placeholder="123456" className="tracking-[0.5em] text-center text-lg" required /></div>
            <Button data-testid="verify-otp-btn" type="submit" className="w-full" disabled={busy || otp.length < 6}>{busy ? "Verifying…" : "Verify & sign in"}</Button>
            <button type="button" data-testid="resend-otp-btn" onClick={sendOtp} className="text-sm text-primary hover:underline w-full text-center">Resend code</button>
          </form>
        )}
      </div>
    </div>
  );
}
