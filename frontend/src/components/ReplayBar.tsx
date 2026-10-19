import { useEffect, useState } from "react";
import type { ReplayEngine } from "../replay";

/** Steuerleiste der Vorschau: Abspielen, Tempo, Zeitleiste. Rückwärts springen startet die Ansicht neu. */
export function ReplayBar({ engine }: { engine: ReplayEngine }) {
  const [, force] = useState(0);
  useEffect(() => engine.subscribe(() => force((n) => n + 1)), [engine]);
  const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
  const seek = (t: number) => {
    if (t < engine.t) window.dispatchEvent(new CustomEvent("replay-restart", { detail: t }));
    else engine.seekForward(t);
  };
  return (
    <div className="replay-bar" data-testid="replay-bar">
      <button className="btn primary" onClick={() => {
        if (engine.t >= engine.duration) seek(0); else engine.playing = !engine.playing;
        force((n) => n + 1);
      }} aria-label={engine.playing ? "Pause" : "Abspielen"}>
        {engine.t >= engine.duration ? "⟲ Von vorn" : engine.playing ? "❚❚ Pause" : "▶ Abspielen"}
      </button>
      <input type="range" min={0} max={engine.duration} step={0.5} value={engine.t} aria-label="Zeitleiste der Aufzeichnung"
        onChange={(e) => seek(Number(e.target.value))} />
      <span className="small replay-time">{fmt(engine.t)} / {fmt(engine.duration)}</span>
      <div className="speeds" role="group" aria-label="Tempo">
        {[1, 2, 4].map((s) => (
          <button key={s} className={`btn ${engine.speed === s ? "primary" : "ghost"}`} onClick={() => { engine.speed = s; force((n) => n + 1); }}>{s}×</button>
        ))}
      </div>
    </div>
  );
}
