import { createContext, useContext, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

const OptionsCtx = createContext(null);
export const useOptions = () => useContext(OptionsCtx);

export function OptionsProvider({ children }) {
  const [options, setOptions] = useState({});
  const [customFields, setCustomFields] = useState([]);

  const refresh = useCallback(() => {
    api.get("/options").then((r) => setOptions(r.data)).catch(() => {});
    api.get("/custom-fields").then((r) => setCustomFields(r.data)).catch(() => {});
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const labels = useCallback((type) => (options[type] || []).map((o) => o.label), [options]);
  const list = useCallback((type) => options[type] || [], [options]);

  return <OptionsCtx.Provider value={{ options, customFields, refresh, labels, list }}>{children}</OptionsCtx.Provider>;
}
