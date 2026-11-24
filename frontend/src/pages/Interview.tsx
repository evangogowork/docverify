import { marked } from "marked";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import raw from "../../../docs/interview.md?raw";

type QA = { q: string; html: string };
type Group = { title: string; items: QA[] };

// docs/interview.md: "## 分组" headings, "### 问题" headings, the body under each question is its answer.
function parse(md: string): { intro: string; groups: Group[] } {
  const groups: Group[] = [];
  let intro = "";
  let cur: Group | null = null;
  let q: { q: string; body: string[] } | null = null;
  const flush = () => { if (q && cur) cur.items.push({ q: q.q, html: marked.parse(q.body.join("\n")) as string }); q = null; };
  for (const line of md.split("\n")) {
    if (line.startsWith("## ")) { flush(); cur = { title: line.slice(3).trim(), items: [] }; groups.push(cur); }
    else if (line.startsWith("### ")) { flush(); q = { q: line.slice(4).trim(), body: [] }; }
    else if (q) q.body.push(line);
    else if (!cur && !line.startsWith("# ")) intro += line + "\n";
  }
  flush();
  return { intro: marked.parse(intro) as string, groups };
}

export default function Interview() {
  const { intro, groups } = useMemo(() => parse(raw), []);
  const [all, setAll] = useState(false);
  const total = groups.reduce((n, g) => n + g.items.length, 0);
  return (
    <div className="interview">
      <div className="learn-tabs"><Link to="/learn">教学模式</Link><Link to="/learn/interview" className="active">面试题</Link>
        <Link to="/learn/problems">日常问题</Link></div>
      <h1>面试题 <span className="muted small">{total} 题 · 点开看答案</span></h1>
      <div className="toolbar">
        <button onClick={() => setAll(!all)}>{all ? "全部收起" : "全部展开"}</button>
      </div>
      <div className="md" dangerouslySetInnerHTML={{ __html: intro }} />
      {groups.map((g) => (
        <section key={g.title}>
          <h2>{g.title}</h2>
          {g.items.map((it) => (
            <details className="qa card" key={it.q + String(all)} open={all}>
              <summary>{it.q}</summary>
              <div className="answer md" dangerouslySetInnerHTML={{ __html: it.html }} />
            </details>
          ))}
        </section>
      ))}
    </div>
  );
}
