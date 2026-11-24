import { useState } from "react";
import { login, type Session } from "../api";
import { ErrorLine } from "../components/ui";

const PLATFORMS = ["ecommerce", "ads", "live", "payments"];

export default function Login({ onLogin }: { onLogin: (s: Session) => void }) {
  const [kind, setKind] = useState<"platform" | "reviewer">("platform");
  const [id, setId] = useState("ecommerce-demo");
  const [secret, setSecret] = useState("");
  const [error, setError] = useState("");
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try { onLogin(await login(kind, id, secret)); } catch (err: any) { setError(err.message); }
  };
  const pick = (k: "platform" | "reviewer") => { setKind(k); setId(k === "platform" ? "ecommerce-demo" : "reviewer"); setSecret(""); };
  return (
    <div className="narrow">
      <h1>登录</h1>
      <div className="tabs">
        <button className={kind === "platform" ? "on" : ""} onClick={() => pick("platform")}>业务平台（API client）</button>
        <button className={kind === "reviewer" ? "on" : ""} onClick={() => pick("reviewer")}>审核员</button>
      </div>
      <form onSubmit={submit} className="form">
        <label>{kind === "platform" ? "client_id" : "用户名"}
          {kind === "platform"
            ? <select value={id} onChange={(e) => setId(e.target.value)} name="client_id">
                {PLATFORMS.map((p) => <option key={p} value={`${p}-demo`}>{p}-demo</option>)}
              </select>
            : <input value={id} onChange={(e) => setId(e.target.value)} name="username" />}
        </label>
        <label>{kind === "platform" ? "client_secret" : "密码"}
          <input type="password" value={secret} onChange={(e) => setSecret(e.target.value)} name="secret" />
        </label>
        <button type="submit" className="primary">登录</button>
        <ErrorLine error={error} />
      </form>
      <p className="muted small">本地演示身份（明显的占位值，只在 <code>DOCVERIFY_SEED_DEMO=1</code> 时创建）：
        平台 <code>&lt;platform&gt;-demo</code> / <code>demo-secret-&lt;platform&gt;</code>；审核员 <code>reviewer</code> / <code>reviewer-demo-pass</code>。</p>
    </div>
  );
}
