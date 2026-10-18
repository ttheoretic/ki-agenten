// Dünner API-Client. Das Owner-Token kommt aus dem URL-Fragment (#token=…) und liegt danach nur im sessionStorage.

const TOKEN_KEY = "aico-owner-token";

export function readToken(): string | null {
  const m = window.location.hash.match(/token=([^&]+)/);
  if (m) {
    const t = decodeURIComponent(m[1]);
    try { sessionStorage.setItem(TOKEN_KEY, t); } catch { /* Speicher nicht verfügbar */ }
    history.replaceState(null, "", window.location.pathname + window.location.search);
    return t;
  }
  try { return sessionStorage.getItem(TOKEN_KEY); } catch { return null; }
}

export function saveToken(t: string) {
  try { sessionStorage.setItem(TOKEN_KEY, t); } catch { /* ignore */ }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export class Api {
  constructor(public token: string, private base = "") {}

  private async req<T>(method: string, path: string, body?: unknown): Promise<T> {
    const res = await fetch(this.base + path, {
      method,
      headers: { Authorization: `Bearer ${this.token}`, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try { const j = await res.json(); detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { /* kein JSON */ }
      throw new ApiError(res.status, detail);
    }
    const ct = res.headers.get("content-type") || "";
    return (ct.includes("application/json") ? res.json() : res.text()) as Promise<T>;
  }

  get<T>(path: string) { return this.req<T>("GET", path); }
  post<T>(path: string, body?: unknown) { return this.req<T>("POST", path, body ?? {}); }
  streamUrl(afterId: number) {
    return `${this.base}/api/events/stream?after_id=${afterId}&token=${encodeURIComponent(this.token)}`;
  }
}
