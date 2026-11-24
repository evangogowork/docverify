import { useEffect, useState } from "react";
import parts from "./parts.json";

const exists = new Map<string, Promise<boolean>>();
function check(src: string) {
  if (!exists.has(src)) exists.set(src, fetch(src, { method: "HEAD" }).then((r) => r.ok && (r.headers.get("content-type") || "").includes("video")).catch(() => false));
  return exists.get(src)!;
}

/** "看讲解视频" for one part. Plays /videos/<part>.mp4; shows 视频待生成 when the file is not there. */
export function VideoButton({ part, open, onOpen }: { part: string; open: boolean; onOpen: (p: string | null) => void }) {
  return (
    <button className="video-btn" data-part={part} onClick={() => onOpen(open ? null : part)}>
      {open ? "收起视频" : "看讲解视频"}
    </button>
  );
}

export function VideoPlayer({ part }: { part: string }) {
  const src = `/videos/${part}.mp4`;
  const [ok, setOk] = useState<boolean | null>(null);
  useEffect(() => { let alive = true; check(src).then((v) => alive && setOk(v)); return () => { alive = false; }; }, [src]);
  const title = (parts as any[]).find((p) => p.part === part)?.title || part;
  if (ok === null) return <div className="video-missing">检查视频…</div>;
  if (!ok) return <div className="video-missing" data-testid="video-missing">视频待生成：{title}（{part}.mp4）</div>;
  return <div className="video-box"><video src={src} controls preload="metadata" data-testid="video" /></div>;
}
