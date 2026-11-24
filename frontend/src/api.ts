export type Session = { token: string; role: string; sub: string; platform?: string | null };

const KEY = "docverify.session";

export function getSession(): Session | null {
  try { return JSON.parse(localStorage.getItem(KEY) || "null"); } catch { return null; }
}
export function setSession(s: Session | null) {
  try { s ? localStorage.setItem(KEY, JSON.stringify(s)) : localStorage.removeItem(KEY); } catch { /* private mode */ }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  const s = getSession();
  const headers = new Headers(init.headers);
  if (s) headers.set("Authorization", `Bearer ${s.token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const r = await fetch(path, { ...init, headers });
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j); } catch { /* not json */ }
    throw new ApiError(r.status, msg);
  }
  const ct = r.headers.get("content-type") || "";
  return (ct.includes("json") ? r.json() : (r.text() as any)) as T;
}

export async function login(kind: "platform" | "reviewer", id: string, secret: string): Promise<Session> {
  const res = kind === "platform"
    ? await api<{ access_token: string }>("/v1/auth/token", { method: "POST", body: JSON.stringify({ client_id: id, client_secret: secret }) })
    : await api<{ access_token: string }>("/v1/auth/login", { method: "POST", body: JSON.stringify({ username: id, password: secret }) });
  const claims = JSON.parse(atob(res.access_token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
  const s = { token: res.access_token, role: claims.role, sub: claims.sub, platform: claims.platform };
  setSession(s);
  return s;
}
