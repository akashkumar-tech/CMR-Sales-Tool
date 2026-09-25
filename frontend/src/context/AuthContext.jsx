import { createContext, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";

const AuthCtx = createContext(null);
export const useAuth = () => useContext(AuthCtx);
const MANAGER_ROLES = ["admin", "manager"];

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("beet_token");
    if (!token) { setLoading(false); return; }
    api.get("/auth/me").then((r) => setUser(r.data)).catch(() => localStorage.removeItem("beet_token")).finally(() => setLoading(false));
  }, []);

  const requestOtp = async (email) => (await api.post("/auth/request-otp", { email })).data;
  const verifyOtp = async (email, otp) => {
    const { data } = await api.post("/auth/verify-otp", { email, otp });
    localStorage.setItem("beet_token", data.token);
    setUser(data.user);
    return data.user;
  };
  const logout = () => {
    // Revoke this session server-side (explicit header: the token is removed from storage right below).
    const token = localStorage.getItem("beet_token");
    if (token) api.post("/auth/logout", null, { headers: { Authorization: `Bearer ${token}` } }).catch(() => {});
    localStorage.removeItem("beet_token"); setUser(null);
  };

  return (
    <AuthCtx.Provider value={{
      user, loading, requestOtp, verifyOtp, logout,
      isManager: MANAGER_ROLES.includes(user?.role),
      isAdmin: user?.role === "admin",
    }}>{children}</AuthCtx.Provider>
  );
}
