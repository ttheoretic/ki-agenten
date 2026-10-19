import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { Api, readToken, saveToken } from "./api";
import { AppContext, type Panel } from "./context";
import { LiveConnection } from "./live";
import { initialState, reducer } from "./store";
import { Header } from "./components/Header";
import { CompanyMap } from "./components/CompanyMap";
import { ActivityFeed } from "./components/ActivityFeed";
import { SidePanel } from "./components/SidePanel";
import { BottomTabs } from "./components/BottomTabs";
import { ReplayBar } from "./components/ReplayBar";
import { ReplayApi, type ApiLike, type ReplayEngine } from "./replay";

function Login({ onToken }: { onToken: (t: string) => void }) {
  const [value, setValue] = useState("");
  return (
    <div className="login">
      <div className="login-card">
        <h1>Control-Center</h1>
        <p>Bitte das Owner-Token eingeben. Es wird beim Start von <code>aicompany serve</code> im Terminal angezeigt
          und liegt in <code>data/&lt;modus&gt;/owner_token</code>.</p>
        <form onSubmit={(e) => { e.preventDefault(); if (value.trim()) onToken(value.trim()); }}>
          <input autoFocus type="password" placeholder="Owner-Token" value={value} onChange={(e) => setValue(e.target.value)} aria-label="Owner-Token" />
          <button className="btn primary" type="submit">Verbinden</button>
        </form>
      </div>
    </div>
  );
}

export default function App({ replay }: { replay?: ReplayEngine }) {
  const [token, setToken] = useState<string | null>(() => (replay ? "vorschau" : readToken()));
  const [state, dispatch] = useReducer(reducer, initialState);
  const [panel, setPanel] = useState<Panel | null>(null);
  const [toasts, setToasts] = useState<{ id: number; msg: string; kind: string }[]>([]);
  const [now, setNow] = useState(() => (replay ? replay.now() : Date.now()));
  const live = useRef<LiveConnection | null>(null);
  const api: ApiLike | null = useMemo(() => (replay ? new ReplayApi(replay) : token ? new Api(token) : null), [token, replay]);

  useEffect(() => {
    // Token kann auch nachträglich per Link (#token=…) übergeben werden
    const onHash = () => { const t = readToken(); if (t) setToken(t); };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    if (replay) return replay.subscribe(() => setNow(replay.now()));  // virtuelle Uhr der Aufzeichnung
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [replay]);

  useEffect(() => {
    if (!api) return;
    const conn = new LiveConnection(api instanceof ReplayApi
      ? { api, dispatch, makeEventSource: api.makeEventSource, pollMs: 1000, refreshDebounceMs: 150 }
      : { api, dispatch });
    live.current = conn;
    void conn.start();
    return () => conn.stop();
  }, [api]);

  useEffect(() => {
    if (state.error?.includes("Owner-Token")) setToken(null);  // 401: Token ungültig → erneut abfragen
  }, [state.error]);

  const toast = useCallback((msg: string, kind: "ok" | "error" = "ok") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, msg, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5000);
  }, []);

  const refresh = useCallback(async () => { await live.current?.refresh(); }, []);

  if (!token || !api) return <Login onToken={(t) => { saveToken(t); setToken(t); }} />;

  const ctx = { api, state, refresh, open: setPanel, toast, now, replay: !!replay };
  const snap = state.snapshot;
  return (
    <AppContext.Provider value={ctx}>
      <div className="app">
        {replay ? (
          <div className="demo-banner" role="status">VORSCHAU – Aufzeichnung eines echten Dry-Runs im Zeitraffer. Agentenantworten sind simuliert,
            Eigentümer-Entscheidungen und Kennzahlen sind DEMO-Werte. Buttons sind hier deaktiviert.</div>
        ) : snap?.simulated && (
          <div className="demo-banner" role="status">DRY-RUN / DEMO-MODUS – alle Agentenantworten und Kosten sind simuliert. Es finden keine echten API-Aufrufe statt.</div>
        )}
        <Header />
        {!snap ? (
          <div className="loading">{state.conn === "offline" ? `Backend nicht erreichbar: ${state.error ?? ""}` : "Verbinde mit dem Backend …"}</div>
        ) : (
          <>
            <main className="main-grid">
              <section className="map-section"><CompanyMap /></section>
              <aside className="feed-section"><ActivityFeed /></aside>
            </main>
            <BottomTabs />
          </>
        )}
        {panel && <SidePanel panel={panel} onClose={() => setPanel(null)} />}
        {replay && <ReplayBar engine={replay} />}
        <div className="toasts" aria-live="polite">
          {toasts.map((t) => <div key={t.id} className={`toast ${t.kind}`}>{t.msg}</div>)}
        </div>
      </div>
    </AppContext.Provider>
  );
}
