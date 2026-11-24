import { useEffect, useState } from "react";
import { getSession } from "../api";
import { Conf } from "./ui";

export function FieldsTable({ extraction }: { extraction: any }) {
  const fields = extraction?.fields || {};
  const names = ["business_name", "registration_number", "address", "issue_date", "expiry_date", "issuing_authority"];
  return (
    <table className="grid">
      <thead><tr><th>字段</th><th>抽取值</th><th>置信度</th></tr></thead>
      <tbody>
        {names.map((n) => (
          <tr key={n} className={fields[n] ? "" : "missing"} data-field={n}>
            <td><code>{n}</code></td><td data-value={n}>{fields[n]?.value ?? <em>未抽到</em>}</td><td data-conf={n} data-low={String(fields[n] ? fields[n].confidence < 0.8 : true)}><Conf value={fields[n]?.confidence} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function ChecksTable({ checks }: { checks: any[] }) {
  if (!checks?.length) return <p className="muted">还没有校验结果</p>;
  return (
    <table className="grid">
      <thead><tr><th>检查</th><th>类型</th><th>结果</th><th>说明</th></tr></thead>
      <tbody>
        {checks.map((c) => (
          <tr key={c.name} className={c.passed ? "" : "fail"} data-check={c.name} data-passed={String(c.passed)}>
            <td><code>{c.name}</code></td><td>{c.kind}</td><td>{c.passed ? "通过" : "失败"}</td><td className="muted">{c.detail}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function MatchesTable({ matches }: { matches: any[] }) {
  if (!matches?.length) return <p className="muted">没有匹配结果</p>;
  return (
    <table className="grid">
      <thead><tr><th>字段</th><th>文档</th><th>账户记录</th><th>方法</th><th>分数</th></tr></thead>
      <tbody>
        {matches.map((m) => (
          <tr key={m.field} data-match={m.field}><td><code>{m.field}</code></td><td>{m.document_value}</td><td>{m.account_value}</td>
            <td>{m.method}</td><td data-score={m.field}><Conf value={m.score} /></td></tr>
        ))}
      </tbody>
    </table>
  );
}

export function DocumentPreview({ caseId, contentType }: { caseId: string; contentType?: string }) {
  // Fetched with the Authorization header (never a token in the URL), shown from a blob: URL.
  const [url, setUrl] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => {
    let revoke = "";
    const s = getSession();
    fetch(`/v1/cases/${caseId}/document`, { headers: s ? { Authorization: `Bearer ${s.token}` } : {} })
      .then((r) => (r.ok ? r.blob() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((b) => { revoke = URL.createObjectURL(b); setUrl(revoke); })
      .catch((e) => setErr(String(e.message || e)));
    return () => { if (revoke) URL.revokeObjectURL(revoke); };
  }, [caseId]);
  if (err) return <p className="error">原始文档加载失败：{err}</p>;
  if (!url) return <p className="muted">加载原始文档…</p>;
  if (contentType?.startsWith("image/")) return <img className="doc" src={url} alt="原始文档" />;
  if (contentType === "application/pdf") return <iframe className="doc" src={url} title="原始文档" />;
  return <a href={url} download>下载原始文档（{contentType}）</a>;
}
