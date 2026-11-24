import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { ErrorLine } from "../components/ui";

export default function ReviewQueue() {
  const [q, setQ] = useState<any>({ items: [] });
  const [error, setError] = useState("");
  const nav = useNavigate();
  useEffect(() => {
    let alive = true;
    const load = () => api("/v1/review/queue").then((x) => alive && setQ(x)).catch((e) => alive && setError(e.message));
    load();
    const t = setInterval(load, 1500);
    return () => { alive = false; clearInterval(t); };
  }, []);
  const claim = async () => {
    setError("");
    try { const c = await api<any>("/v1/review/claim", { method: "POST" }); nav(`/review/${c.case_id}`); }
    catch (e: any) { setError(e.message); }
  };
  return (
    <div>
      <h1>审核队列</h1>
      <p className="muted">最小堆按 <code>风险分 × {q.aging_seconds_per_point ?? 60} 秒 + 已等待秒数</code> 排序：高风险插队，等久了的低风险也会轮到。</p>
      <button className="primary" onClick={claim} data-testid="claim-next">领取下一个</button>
      <ErrorLine error={error} />
      <table className="grid">
        <thead><tr><th>#</th><th>case</th><th>账户</th><th>风险</th><th>等待</th><th>优先级</th><th>原因</th></tr></thead>
        <tbody>{q.items.map((c: any, i: number) => (
          <tr key={c.case_id}><td>{i + 1}</td><td><Link to={`/cases/${c.case_id}`}>{c.case_id}</Link></td><td>{c.account_id}</td>
            <td>{c.risk_score}</td><td>{Math.round(c.waited)}s</td><td>{c.priority}</td><td className="muted">{(c.reasons || []).join(", ")}</td></tr>
        ))}</tbody>
      </table>
    </div>
  );
}
