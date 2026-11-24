import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { Card, ErrorLine, StateBadge } from "../components/ui";
import { ChecksTable, DocumentPreview, FieldsTable, MatchesTable } from "../components/Extraction";

const REASONS: Record<string, string[]> = {
  APPROVED: ["documents verified by reviewer"],
  REJECTED: ["business name does not match account", "document appears altered", "expired document"],
  RESUBMIT_REQUESTED: ["image unreadable, please rescan", "wrong document type", "page missing"],
};

export default function ReviewCase() {
  const { id = "" } = useParams();
  const [c, setC] = useState<any>(null);
  const [decision, setDecision] = useState("APPROVED");
  const [reason, setReason] = useState(REASONS.APPROVED[0]);
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const nav = useNavigate();
  useEffect(() => { api(`/v1/review/cases/${id}`).then(setC).catch((e) => setError(e.message)); }, [id]);
  const submit = async () => {
    setError("");
    try {
      await api(`/v1/review/cases/${id}/decision`, { method: "POST", body: JSON.stringify({ decision, reason, notes }) });
      nav(`/cases/${id}`);
    } catch (e: any) { setError(e.message); }
  };
  if (!c) return <div><ErrorLine error={error} /><p className="muted">加载中…</p></div>;
  const failed = (c.validation || []).filter((x: any) => !x.passed);
  return (
    <div>
      <h1>审核 {c.case_id} <StateBadge state={c.state} /></h1>
      <p className="muted">{c.account_id} · {c.doc_type} · 风险 {c.risk_score} · 领取人 {c.claimed_by || "—"}</p>
      <ErrorLine error={error} />
      <div className="cols">
        <Card title="原始文档"><DocumentPreview caseId={c.case_id} contentType={c.content_type} /></Card>
        <div>
          <Card title="抽取字段与置信度"><FieldsTable extraction={c.extraction} /></Card>
          <Card title={`失败项（${failed.length}）`}><ChecksTable checks={failed} /></Card>
          <Card title="与账户记录比对"><MatchesTable matches={c.matches} /></Card>
        </div>
      </div>
      <Card title="审核结论">
        <div className="form inline">
          <select value={decision} onChange={(e) => { setDecision(e.target.value); setReason(REASONS[e.target.value][0]); }} name="decision">
            <option value="APPROVED">通过</option><option value="REJECTED">驳回</option><option value="RESUBMIT_REQUESTED">要求重新提交</option>
          </select>
          <select value={reason} onChange={(e) => setReason(e.target.value)} name="reason">
            {REASONS[decision].map((r) => <option key={r}>{r}</option>)}
          </select>
          <input placeholder="备注" value={notes} onChange={(e) => setNotes(e.target.value)} name="notes" />
          <button className="primary" onClick={submit} data-testid="submit-decision">提交结论</button>
        </div>
      </Card>
    </div>
  );
}
