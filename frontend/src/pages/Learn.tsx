import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { code } from "../code";
import { Card, ErrorLine, Expand, Json, StateBadge, fmtTime } from "../components/ui";
import { ChecksTable, FieldsTable, MatchesTable } from "../components/Extraction";
import { PANEL_PARTS, STAGES } from "../learn/stages";
import { VideoButton, VideoPlayer } from "../learn/VideoButton";

const SCENARIOS = [
  ["lowres", "低分辨率扫描件：置信度不够，进人审"],
  ["clean", "干净扫描件：一路自动通过"],
  ["tampered", "注册号校验位被改：自动驳回"],
];

function Sources({ ids }: { ids: string[] }) {
  return (
    <div className="src">
      看源码：{ids.map((id) => { const c = code(id); return <a key={id} href={c.href} target="_blank" rel="noreferrer" data-anchor={id}>{c.label}</a>; })}
    </div>
  );
}

function StageData({ id, run }: { id: string; run: any }) {
  const d = run.stages.find((s: any) => s.id === id)?.data;
  if (!d) return <p className="muted">这一步还没走到。</p>;
  const audit = d.audit && <Expand name={`${id}-audit`} label="这一步的 MySQL 审计行" value={d.audit} />;
  switch (id) {
    case "upload":
      return <><div className="kv"><span>S3 key <code data-hl="s3-key">{d.s3_key}</code></span><span>sha256 <code data-hl="sha">{d.sha256.slice(0, 16)}…</code></span><span>平台 <b>{d.platform}</b></span></div>{audit}</>;
    case "s3":
      return <><div className="kv"><span>大小 <b data-hl="s3-size">{d.size}</b> 字节</span><span>事件 <code data-hl="s3-event">{d.event}</code></span></div>
        <Expand name="s3-metadata" label="对象元数据" value={d.metadata} /></>;
    case "lambda":
      return <><h4>CloudWatch 日志（这次调用）</h4>
        <div className="loglines" data-hl="lambda-log">{(d.logs || []).length ? d.logs.map((l: string, i: number) => <code key={i} data-log={l.startsWith("{") ? "json" : "meta"}>{l}</code>) : <span className="muted">（日志还没到）</span>}</div>{audit}</>;
    case "sqs":
      return <>{(d.receipts || []).map((r: any, i: number) => (
        <div key={r.id} className="receipt" data-receipt={i}>
          <div className="kv"><span>第 <b data-hl="receive-count">{r.receive_count}</b> 次投递</span><span>分组 <code data-hl="group-id">{r.group_id}</code></span>
            <span>序列号 <code>{r.sequence_number.slice(-8)}</code></span><span>worker <code>{r.worker_id}</code></span>
            <span>结果 <b data-testid="receipt-outcome">{r.outcome}</b></span></div>
          <Expand name={`sqs-body-${i}`} label="SQS 消息体" value={r.body} />
        </div>))}</>;
    case "extraction": return <><FieldsTable extraction={d.extraction} />{audit}</>;
    case "validation": return <><ChecksTable checks={d.checks} />{audit}</>;
    case "decision":
      return <><div className="kv"><span>结论 <b data-hl="decision">{d.decision?.decision}</b></span><span>风险分 <b data-hl="risk">{d.decision?.risk}</b></span>
        <span>原因 <code data-hl="reasons">{(d.decision?.reasons || []).join(", ") || "全部通过"}</code></span></div>
        <MatchesTable matches={d.matches} />{audit}</>;
    case "review":
      return <><div className="kv"><span>风险分 <b data-hl="review-risk">{d.risk_score}</b></span><span>领取人 <code>{d.claimed_by || "—"}</code></span>
        {d.review && <span>结论 <b data-hl="review-decision">{d.review.decision}</b>（{d.review.reviewer}）</span>}</div>
        <details className="jsonbox" data-json="review-view"><summary>打开审核视图：字段、置信度、失败项</summary>
          <FieldsTable extraction={run.case.extraction} /><ChecksTable checks={(run.case.validation || []).filter((c: any) => !c.passed)} /></details>{audit}</>;
    case "callback":
      return <>{(d.outbox || []).map((o: any) => (
        <div key={o.id} data-outbox={o.status}>
          <div className="kv"><span>状态 <b>{o.status}</b></span><span>尝试 <b>{o.attempts}</b> 次</span><span>{o.delivered_at ? "已送达" : o.dead ? "放弃" : "重试中"}</span></div>
          {(o.attempts_log || []).map((a: any, i: number) => <div key={i} className="kv"><span>HTTP <b>{a.http_status ?? "—"}</b></span><span>签名 <code data-hl={`signature-${o.status}`}>{a.signature}</code></span></div>)}
          <Expand name={`payload-${o.status}`} label="回调 payload" value={o.payload} />
        </div>))}
        <h4>平台那边收到的</h4>
        {(d.received_by_platform || []).map((r: any, i: number) => <div key={i} className="kv"><span>{r.payload.status}</span><span>验签 <b data-hl={`verify-${r.payload.status}`}>{r.result}</b></span><span>{r.event_id}</span></div>)}</>;
    default: return <Json value={d} />;
  }
}

export default function Learn() {
  const [scenario, setScenario] = useState("lowres");
  const [run, setRun] = useState<any>(null);
  const [caseId, setCaseId] = useState("");
  const [selected, setSelected] = useState("upload");
  const [follow, setFollow] = useState(true);
  const [video, setVideo] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [evalReport, setEval] = useState<any>(null);
  const timer = useRef<number>();

  useEffect(() => {
    if (!caseId) return;
    let alive = true;
    const load = async () => {
      try {
        const r = await api(`/v1/learn/runs/${caseId}`);
        if (!alive) return;
        setRun(r);
        if (follow) {
          const active = r.stages.find((s: any) => s.status === "active") || [...r.stages].reverse().find((s: any) => s.status === "done");
          if (active) setSelected(active.id);
        }
      } catch (e: any) { if (alive) setError(e.message); }
    };
    load();
    timer.current = window.setInterval(load, 700);
    return () => { alive = false; clearInterval(timer.current); };
  }, [caseId, follow]);

  const start = async () => {
    setError(""); setRun(null); setFollow(true); setSelected("upload");
    try { const r = await api<any>("/v1/learn/runs", { method: "POST", body: JSON.stringify({ scenario }) }); setCaseId(r.case_id); }
    catch (e: any) { setError(e.message); }
  };
  const review = async (decision: string) => {
    try { await api(`/v1/learn/runs/${caseId}/review`, { method: "POST", body: JSON.stringify({ decision }) }); }
    catch (e: any) { setError(e.message); }
  };
  const replay = async () => {
    try { await api(`/v1/learn/runs/${caseId}/replay`, { method: "POST" }); setFollow(false); setSelected("sqs"); }
    catch (e: any) { setError(e.message); }
  };
  const loadEval = async () => { try { setEval(await api("/v1/learn/eval")); } catch (e: any) { setError(e.message); } };

  const status = (id: string) => run?.stages.find((s: any) => s.id === id)?.status || "pending";
  const stage = STAGES.find((s) => s.id === selected)!;
  const inReview = run?.case?.state === "IN_REVIEW";

  return (
    <div>
      <div className="learn-tabs"><Link to="/learn" className="active">教学模式</Link><Link to="/learn/interview" id="tab-interview">面试题</Link><Link to="/learn/problems" id="tab-problems">日常问题</Link></div>
      <h1>教学模式：一份证明材料的完整旅程</h1>
      <p className="muted">点「提交样例」，后端会真的走一遍：API → S3 → Lambda → SQS FIFO → worker → DynamoDB / MySQL → 回调。左边哪一步亮，就是请求现在走到了哪里；状态全部来自后端轮询，不是前端动画。每一步都能跳到 GitHub 上对应的源码行，也能看这一段的讲解视频。</p>
      <div className="toolbar">
        <select id="learn-scenario" value={scenario} onChange={(e) => setScenario(e.target.value)}>
          {SCENARIOS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <button id="learn-submit" className="primary" onClick={start}>提交样例</button>
        {run && <span>case <Link to={`/cases/${caseId}`}><code>{caseId}</code></Link> <StateBadge state={run.case.state} /></span>}
        {run && <button id="learn-replay" onClick={replay} disabled={!["QUEUED", "EXTRACTED", "VALIDATED", "IN_REVIEW", "APPROVED", "REJECTED"].includes(run.case.state)}>再投递一条重复消息</button>}
        <label className="small" style={{ flexDirection: "row", alignItems: "center" }}><input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> 跟随进度</label>
      </div>
      <ErrorLine error={error} />
      <div className="learn">
        <ol className="timeline" id="learn-timeline">
          {STAGES.map((s, i) => (
            <li key={s.id} data-stage={s.id} data-status={status(s.id)} className={selected === s.id ? "selected" : ""}
                onClick={() => { setFollow(false); setSelected(s.id); }}>
              <span className="dot" />
              <span className="t">{i + 1}. {s.title}<span className="sub">{s.sub}{run?.stages.find((x: any) => x.id === s.id)?.at ? ` · ${fmtTime(run.stages.find((x: any) => x.id === s.id).at)}` : ""}</span></span>
            </li>
          ))}
        </ol>
        <div>
          <Card title={<span>{stage.title} <span className="muted small">{stage.sub}</span></span>}
                right={<VideoButton part={stage.part} open={video === stage.part} onOpen={setVideo} />}>
            <div className="stage-detail" id="stage-detail" data-selected={stage.id}>
              {video === stage.part && <VideoPlayer part={stage.part} />}
              <p>{stage.explain}</p>
              <Sources ids={stage.anchors} />
              {stage.id === "review" && inReview && (
                <div className="toolbar" id="learn-review-actions">
                  <span>你现在是审核员：</span>
                  <button onClick={() => review("APPROVED")} id="learn-approve">通过</button>
                  <button onClick={() => review("REJECTED")}>驳回</button>
                  <button onClick={() => review("RESUBMIT_REQUESTED")}>要求重新提交</button>
                </div>
              )}
              {run ? <StageData id={stage.id} run={run} /> : <p className="muted">先点「提交样例」。</p>}
            </div>
          </Card>
          <Card title="DynamoDB 里的这一条 case（权威状态）" right={<VideoButton part={PANEL_PARTS.state} open={video === PANEL_PARTS.state} onOpen={setVideo} />}>
            <div id="panel-state">
              {video === PANEL_PARTS.state && <VideoPlayer part={PANEL_PARTS.state} />}
              <Sources ids={["state-machine", "transition", "test-concurrent-decisions"]} />
              {run ? <>
                <table className="grid"><thead><tr><th>#</th><th>from → to</th><th>actor</th><th>write_id</th></tr></thead>
                  <tbody>{(run.case.history || []).map((h: any, i: number) => <tr key={h.write_id} data-hist={i} data-to={h.to}><td>{i + 1}</td><td><code>{h.from} → {h.to}</code></td><td>{h.actor}</td><td className="mono small">{h.write_id}</td></tr>)}</tbody></table>
                <p className="small muted" data-hl="audit-count">MySQL audit_log 里对应 {run.audit.length} 行，和 history 一一对应（write_id 唯一）。</p>
                <Expand name="ddb-item" label="DynamoDB 里的整条 item" value={run.case} />
              </> : <p className="muted">还没有 case。</p>}
            </div>
          </Card>
          <Card title="评测集和发布门禁" right={<VideoButton part={PANEL_PARTS.eval} open={video === PANEL_PARTS.eval} onOpen={setVideo} />}>
            <div id="panel-eval">
              {video === PANEL_PARTS.eval && <VideoPlayer part={PANEL_PARTS.eval} />}
              <Sources ids={["eval-run", "eval-gate"]} />
              <button onClick={loadEval} id="learn-eval">看最近一次评测报告</button>
              {evalReport && <EvalTable report={evalReport} />}
            </div>
          </Card>
          <Card title="这个页面本身是怎么做的" right={<VideoButton part={PANEL_PARTS.learn} open={video === PANEL_PARTS.learn} onOpen={setVideo} />}>
            <div id="panel-learn">
              {video === PANEL_PARTS.learn && <VideoPlayer part={PANEL_PARTS.learn} />}
              <p className="small">源码里用 <code>@learn:&lt;id&gt;</code> 和 <code>@learn:end &lt;id&gt;</code> 注释圈出关键代码，构建时脚本扫出文件和行号；链接固定到构建时的 commit <code>{__GIT_SHA__.slice(0, 10)}</code>，代码改了也不会错位。</p>
              <Sources ids={["learn-run-api"]} />
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

function EvalTable({ report }: { report: any }) {
  return (
    <div>
      <p className="small">门禁：<b data-testid="gate">{report.gate.passed ? "通过" : "未通过"}</b>　生成于 {report.generated_at}</p>
      <table className="grid">
        <thead><tr><th>类别</th><th>样本</th><th>决策准确率</th><th>错误自动通过</th><th>自动通过率</th></tr></thead>
        <tbody>{Object.entries(report.by_category).map(([k, v]: any) => (
          <tr key={k} data-cat={k}><td>{k}</td><td>{v.n}</td><td data-col="accuracy">{(v.accuracy * 100).toFixed(1)}%</td><td data-col="incorrect">{v.incorrect_auto_approvals}</td><td>{(v.auto_approve_rate * 100).toFixed(1)}%</td></tr>
        ))}</tbody>
      </table>
    </div>
  );
}
