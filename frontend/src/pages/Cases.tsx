import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { ErrorLine, StateBadge, fmtTime } from "../components/ui";

export default function Cases() {
  const [items, setItems] = useState<any[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    const load = () => api<any[]>("/v1/cases").then((x) => alive && setItems(x)).catch((e) => alive && setError(e.message));
    load();
    const t = setInterval(load, 1500);
    return () => { alive = false; clearInterval(t); };
  }, []);
  return (
    <div>
      <h1>Case 列表</h1>
      <ErrorLine error={error} />
      <table className="grid">
        <thead><tr><th>case</th><th>平台</th><th>账户</th><th>类型</th><th>轮次</th><th>状态</th><th>风险</th><th>更新</th></tr></thead>
        <tbody>
          {items.map((c) => (
            <tr key={c.case_id}>
              <td><Link to={`/cases/${c.case_id}`}>{c.case_id}</Link></td><td>{c.platform}</td><td>{c.account_id}</td>
              <td>{c.doc_type}</td><td>{c.round}</td><td><StateBadge state={c.state} /></td><td>{c.risk_score ?? ""}</td>
              <td className="muted">{fmtTime(c.updated_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
