import { StrictMode, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { ReplayEngine, type ReplayData } from "./replay";
import "./styles.css";


/** Vorschau-Build: lädt die Aufzeichnung und spielt sie ab; Zurückspulen startet die Ansicht neu. */
function ReplayRoot({ data }: { data: ReplayData }) {
  const [start, setStart] = useState({ t: 0, n: 0 });
  const engine = useMemo(() => new ReplayEngine(data, start.t), [data, start]);
  useEffect(() => {
    engine.start();
    return () => engine.stop();
  }, [engine]);
  useEffect(() => {
    const h = (e: Event) => setStart((s) => ({ t: (e as CustomEvent<number>).detail, n: s.n + 1 }));
    window.addEventListener("replay-restart", h);
    return () => window.removeEventListener("replay-restart", h);
  }, []);
  return <App key={start.n} replay={engine} />;
}

const root = createRoot(document.getElementById("root")!);
if (__REPLAY__) {
  fetch("./replay.json")
    .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then((data: ReplayData) => root.render(<StrictMode><ReplayRoot data={data} /></StrictMode>))
    .catch((e) => root.render(<p style={{ padding: 24 }}>Aufzeichnung konnte nicht geladen werden: {String(e)}</p>));
} else {
  root.render(<StrictMode><App /></StrictMode>);
}
