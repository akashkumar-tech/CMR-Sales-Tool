import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const api = axios.create({ baseURL: API });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("beet_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Session ended (expired, revoked by logout, invalid, or account deactivated): go back to login
// instead of leaving pages silently empty. Auth endpoints report their own errors on the login screen.
api.interceptors.response.use(undefined, (error) => {
  const status = error?.response?.status;
  const detail = error?.response?.data?.detail;
  const url = error?.config?.url || "";
  const sessionEnded = status === 401 || (status === 403 && detail === "Account deactivated");
  if (sessionEnded && !url.startsWith("/auth/") && localStorage.getItem("beet_token")) {
    localStorage.removeItem("beet_token");
    if (window.location.pathname !== "/login") window.location.assign("/login?expired=1");
  }
  return Promise.reject(error);
});

export function apiError(e) {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join(" ");
  if (d && typeof d === "object" && d.message) return d.message;
  return e?.message || "Something went wrong";
}

export { API };
