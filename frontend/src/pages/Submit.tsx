import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { ErrorLine } from "../components/ui";

const DOC_TYPES = [["business_license", "营业执照"], ["tax_certificate", "税务登记证"], ["registration_certificate", "注册证书"]];
const SAMPLES = [["clean", "干净扫描件"], ["pdf", "带文字层的 PDF"], ["blur", "模糊扫描件"], ["lowres", "低分辨率"],
  ["tampered", "校验位被改"], ["expired", "已过期"], ["name_mismatch", "名字对不上"], ["unsupported", "不支持的格式"]];

export default function Submit() {
  const [accounts, setAccounts] = useState<any[]>([]);
  const [account, setAccount] = useState("");
  const [docType, setDocType] = useState("business_license");
  const [file, setFile] = useState<File | null>(null);
  const [sample, setSample] = useState("clean");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();
  useEffect(() => {
    api<any[]>("/v1/accounts").then((a) => { setAccounts(a); setAccount(a[0]?.account_id || ""); }).catch((e) => setError(e.message));
  }, []);
  const submit = async (useSample: boolean) => {
    setError(""); setBusy(true);
    try {
      let f = file;
      if (useSample) {
        const r = await fetch(`/v1/samples/${sample}?account_id=${account}&doc_type=${docType}`);
        if (!r.ok) throw new Error(`sample: HTTP ${r.status}`);
        const name = r.headers.get("x-filename") || "sample.bin";
        f = new File([await r.blob()], name, { type: r.headers.get("content-type") || "application/octet-stream" });
      }
      if (!f) throw new Error("请选择文件或用样例");
      const fd = new FormData();
      fd.set("account_id", account); fd.set("doc_type", docType); fd.set("file", f);
      const res = await api<{ case_id: string }>("/v1/cases", { method: "POST", body: fd });
      nav(`/cases/${res.case_id}`);
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };
  return (
    <div className="narrow">
      <h1>提交证明材料</h1>
      <div className="form">
        <label>账户<select value={account} onChange={(e) => setAccount(e.target.value)} name="account">
          {accounts.map((a) => <option key={a.account_id} value={a.account_id}>{a.account_id} · {a.legal_name}</option>)}
        </select></label>
        <label>材料类型<select value={docType} onChange={(e) => setDocType(e.target.value)} name="doc_type">
          {DOC_TYPES.map(([v, l]) => <option key={v} value={v}>{l}（{v}）</option>)}
        </select></label>
        <label>上传文件<input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} name="file" /></label>
        <button className="primary" disabled={busy || !file} onClick={() => submit(false)}>上传</button>
        <div className="or">或者用生成的样例文档</div>
        <label>样例<select value={sample} onChange={(e) => setSample(e.target.value)} name="sample">
          {SAMPLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select></label>
        <button disabled={busy || !account} onClick={() => submit(true)} data-testid="submit-sample">用样例提交</button>
        <ErrorLine error={error} />
      </div>
    </div>
  );
}
