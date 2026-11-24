import anchors from "./generated/anchors.json";

type Anchor = { path: string; start: number; end: number };
const A = anchors as Record<string, Anchor>;

/** GitHub permalink for a source anchor: <repo>/blob/<sha>/<path>#L<start>-L<end>. */
export function code(id: string): { href: string; label: string } {
  const a = A[id];
  if (!a) return { href: "#", label: `missing anchor ${id}` };
  return { href: `${__REPO_URL__}/blob/${__GIT_SHA__}/${a.path}#L${a.start}-L${a.end}`, label: `${a.path}:${a.start}-${a.end}` };
}
