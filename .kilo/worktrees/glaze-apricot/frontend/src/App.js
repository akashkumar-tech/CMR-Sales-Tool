import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { OptionsProvider } from "@/context/OptionsContext";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import LeadsPage from "@/pages/LeadsPage";
import Kanban from "@/pages/Kanban";
import Tasks from "@/pages/Tasks";
import Activities from "@/pages/Activities";
import Demos from "@/pages/Demos";
import CalendarPage from "@/pages/CalendarPage";
import FollowUps from "@/pages/FollowUps";
import Workload from "@/pages/Workload";
import TeamPerformance from "@/pages/TeamPerformance";
import Reports from "@/pages/Reports";
import Settings from "@/pages/Settings";

const MANAGER_ROLES = ["admin", "manager"];

function Protected({ children, manager, admin }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="min-h-screen grid place-items-center text-slate-500">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (manager && !MANAGER_ROLES.includes(user.role)) return <Navigate to="/dashboard" replace />;
  if (admin && user.role !== "admin") return <Navigate to="/dashboard" replace />;
  return <OptionsProvider><Layout>{children}</Layout></OptionsProvider>;
}

function App() {
  return (
    <div className="App">
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Protected><Dashboard /></Protected>} />
            <Route path="/my-leads" element={<Protected><LeadsPage scope="mine" /></Protected>} />
            <Route path="/all-leads" element={<Protected manager><LeadsPage scope="all" /></Protected>} />
            <Route path="/kanban" element={<Protected><Kanban /></Protected>} />
            <Route path="/tasks" element={<Protected><Tasks /></Protected>} />
            <Route path="/activities" element={<Protected><Activities /></Protected>} />
            <Route path="/demos" element={<Protected><Demos /></Protected>} />
            <Route path="/calendar" element={<Protected><CalendarPage /></Protected>} />
            <Route path="/followups" element={<Protected><FollowUps /></Protected>} />
            <Route path="/workload" element={<Protected manager><Workload /></Protected>} />
            <Route path="/team-performance" element={<Protected manager><TeamPerformance /></Protected>} />
            <Route path="/reports" element={<Protected><Reports /></Protected>} />
            <Route path="/settings" element={<Protected><Settings /></Protected>} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </BrowserRouter>
        <Toaster position="top-right" richColors />
      </AuthProvider>
    </div>
  );
}
export default App;
