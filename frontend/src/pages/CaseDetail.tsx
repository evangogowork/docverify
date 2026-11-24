import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, getSession } from "../api";
import { Card, ErrorLine, Json, StateBadge, fmtTime } from "../components/ui";
import { ChecksTable, DocumentPreview, FieldsTable, MatchesTable } from "../components/Extraction";

export default function CaseDetail() {
  const { id = "" } = useParams();
  const [c, setC] = useState<any>(null);
  const [audit, setAudit] = useState<any[]>([]);
  const [cbs, setCbs] = useState<any[]>([]);
  const [error, setError] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [msg, setMsg] = useState("");
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const [cc, aa, bb] = await Promise.all([api(`/v1/cases/${id}`), api<any[]>(`/v1/cases/${id}/audit`), api<any[]>(`/v1/cases/${id}/callbacks`)]);
        if (alive) { setC(cc); setAudit(aa); setCbs(bb); }
      } catch (e: any) { if (alive) setError(e.message); }
    };
    load();
    const t = setInterval(load, 1200);
    return () => { alive = false; clearInterval(t); };
  }, [id]);
  const resubmit = async () => {
    if (!file) return;
    const fd = new FormData(); fd.set("file", file);
    try { await api(`/v1/cases/${id}/resubmit`, { method: "POST", body: fd }); setMsg("已重新提交，进入新一轮"); setFile(null); }
    catch (e: any) { setError(e.message); }
  };
  if (!c) return <div><ErrorLine error={error} /><p className="muted">加载中…</p></div>;
  const isPlatform = getSession()?.role === "platform";
  return (
    <div>
      <h1>{c.case_id} <StateBadge state={c.state} /></h1>
      <p className="muted">{c.platform} · {c.account_id} · {c.doc_type} · 第 {c.round} 轮 · 风险 {c.risk_score ?? "—"}</p>
      <ErrorLine error={error} />
      {c.state === "RESUBMIT_REQUESTED" && isPlatform && (
        <Card title="需要重新提交">
          <p>原因：{(c.decision_detail?.reasons || c.review?.reason ? [c.review?.reason, ...(c.decision_detail?.reasons || [])].filter(Boolean).join("，") : "—")}</p>
          <input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} name="resubmit-file" />
          <button className="primary" disabled={!file} onClick={resubmit}>重新提交</button> {msg}
        </Card>
      )}
      <div className="cols">
        <Card title="原始文档"><DocumentPreview caseId={c.case_id} contentType={c.content_type} /></Card>
        <Card title="抽取字段"><FieldsTable extraction={c.extraction} /></Card>
      </div>
      <div className="cols">
        <Card title="校验"><ChecksTable checks={c.validation} /></Card>
        <Card title="匹配与决策"><MatchesTable matches={c.matches} />{c.decision_detail && <Json value={c.decision_detail} />}
          {c.review && <><h4>人审</h4><Json value={c.review} /></>}</Card>
      </div>
      <Card title="状态转移（MySQL 审计）">
        <table className="grid"><thead><tr><th>时间</th><th>轮次</th><th>from → to</th><th>actor</th><th>原因</th></tr></thead>
          <tbody>{audit.map((r) => <tr key={r.write_id}><td>{fmtTime(r.created_at)}</td><td>{r.round_no}</td>
            <td><code>{r.from_state} → {r.to_state}</code></td><td>{r.actor}</td><td className="muted">{r.reason}</td></tr>)}</tbody></table>
      </Card>
      <Card title="回调">
        <table className="grid"><thead><tr><th>status</th><th>尝试次数</th><th>送达</th><th>最近错误</th></tr></thead>
          <tbody>{cbs.map((r) => <tr key={r.id}><td>{r.status}</td><td>{r.attempts}</td><td>{r.delivered_at ? fmtTime(r.delivered_at) : r.dead ? "放弃" : "重试中"}</td>
            <td className="muted">{r.last_error}</td></tr>)}</tbody></table>
      </Card>
    </div>
  );
}
