/// <reference types="vite/client" />
declare const __GIT_SHA__: string;
declare const __REPO_URL__: string;
declare module "*.md?raw" { const s: string; export default s; }
