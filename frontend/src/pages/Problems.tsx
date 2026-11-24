import { marked } from "marked";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import raw from "../../../docs/problems.md?raw";
import src from "../../../video/problems.src.json";
import { code } from "../code";

type Problem = { key: string; title: string; html: string; meta: any };

// docs/problems.md: one "## qNN 标题" section per problem. Source anchors and the video id come from
// video/problems.src.json, the same file the problem videos are built from.
function parse(md: string): { intro: string; items: Problem[] } {
  const parts = md.split(/\n(?=## q\d\d )/);
  const intro = marked.parse(parts[0].replace(/^# .*\n/, "")) as string;
  const items = parts.slice(1).map((p) => {
    const [head, ...body] = p.split("\n");
    const key = head.slice(3, 6);
    return { key, title: head.slice(3).trim(), html: marked.parse(body.join("\n")) as string,
             meta: (src as any[]).find((s) => s.id.startsWith(key)) };
  });
  return { intro, items };
}

function ProblemVideo({ id }: { id: string }) {
  const [state, setState] = useState<"idle" | "checking" | "ok" | "missing">("idle");
  const url = `/videos/problems/${id}.mp4`;
  const load = () => {
    setState("checking");
    fetch(url, { method: "HEAD" }).then((r) => setState(r.ok && (r.headers.get("content-type") || "").includes("video") ? "ok" : "missing"))
      .catch(() => setState("missing"));
  };
  if (state === "idle") return <button className="video-btn" data-problem-video={id} onClick={load}>看讲解视频</button>;
  if (state === "checking") return <div className="video-missing">检查视频…</div>;
  if (state === "missing") return <div className="video-missing" data-testid="video-missing">视频待生成（{id}.mp4）</div>;
  return <div className="video-box"><video src={url} controls preload="metadata" data-testid="video" /></div>;
}

export default function Problems() {
  const { intro, items } = useMemo(() => parse(raw), []);
  return (
    <div className="interview">
      <div className="learn-tabs"><Link to="/learn">教学模式</Link><Link to="/learn/interview">面试题</Link>
        <Link to="/learn/problems" className="active">日常问题</Link></div>
      <h1>日常问题与解决 <span className="muted small">{items.length} 个 · 现象 → 定位 → 修复 → 证明</span></h1>
      <div className="md" dangerouslySetInnerHTML={{ __html: intro }} />
      {items.map((it) => (
        <details className="problem card qa" key={it.key} data-problem={it.key}>
          <summary>{it.title}</summary>
          <div className="answer">
            {it.meta && <>
              <ProblemVideo id={it.meta.id} />
              <div className="src">看源码：
                {[it.meta.code_from, it.meta.before_from].filter(Boolean).map((f: any, i: number) => {
                  const c = code(f.anchor);
                  return <a key={f.anchor} href={c.href} target="_blank" rel="noreferrer" data-anchor={f.anchor}>{i === 0 ? "修复后" : "修复前"} · {c.label}</a>;
                })}
              </div>
            </>}
            <div className="md" dangerouslySetInnerHTML={{ __html: it.html }} />
          </div>
        </details>
      ))}
    </div>
  );
}
