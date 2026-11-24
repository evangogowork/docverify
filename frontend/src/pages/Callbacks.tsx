import { useEffect, useState } from "react";
import { ErrorLine, fmtTime } from "../components/ui";

export default function Callbacks() {
  const [data, setData] = useState<any>({ items: [] });
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    const load = () => fetch("/mock/received").then((r) => r.json()).then((x) => alive && setData(x)).catch((e) => alive && setError(String(e)));
    load();
    const t = setInterval(load, 1500);
    return () => { alive = false; clearInterval(t); };
  }, []);
  const failNext = async (n: number) => { await fetch("/mock/control", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ fail_next: n }) }); };
  return (
    <div>
      <h1>平台收到的回调</h1>
      <p className="muted">这是仓库自带的 mock 平台（端口 8511）。四个业务平台共用同一份 v1 契约，每条回调都带 HMAC 签名，接收端验签并按 event_id 去重。
        {data.registered ? " webhook 已注册。" : ` 正在注册 webhook… ${data.error || ""}`}</p>
      <button onClick={() => failNext(2)}>让接下来两次投递失败（演示退避重试）</button>
      <ErrorLine error={error} />
      <table className="grid">
        <thead><tr><th>时间</th><th>平台</th><th>event</th><th>case</th><th>status</th><th>接收结果</th><th>签名</th></tr></thead>
        <tbody>{data.items.map((r: any, i: number) => (
          <tr key={i} className={r.result === "ok" ? "" : "fail"}><td>{fmtTime(r.at)}</td><td>{r.platform}</td><td>{r.event_id}</td>
            <td>{r.payload.case_id}</td><td>{r.payload.status}</td><td>{r.result}</td><td className="mono small">{r.signature.slice(0, 40)}…</td></tr>
        ))}</tbody>
      </table>
    </div>
  );
}
