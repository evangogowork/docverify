import { useState } from "react";
import { Link, NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { getSession, setSession, type Session } from "./api";
import Login from "./pages/Login";
import Submit from "./pages/Submit";
import Cases from "./pages/Cases";
import CaseDetail from "./pages/CaseDetail";
import ReviewQueue from "./pages/ReviewQueue";
import ReviewCase from "./pages/ReviewCase";
import Callbacks from "./pages/Callbacks";
import Learn from "./pages/Learn";
import Interview from "./pages/Interview";
import Problems from "./pages/Problems";

export default function App() {
  const [session, set] = useState<Session | null>(getSession());
  const nav = useNavigate();
  const logout = () => { setSession(null); set(null); nav("/login"); };
  const isPlatform = session?.role === "platform";
  const isReviewer = session?.role === "reviewer" || session?.role === "admin";
  return (
    <div className="shell">
      <header className="top">
        <Link to="/" className="brand">docverify</Link>
        <nav>
          {isPlatform && <NavLink to="/submit">提交材料</NavLink>}
          {isPlatform && <NavLink to="/cases">我的 case</NavLink>}
          {isReviewer && <NavLink to="/review">审核队列</NavLink>}
          {isReviewer && <NavLink to="/cases">全部 case</NavLink>}
          <NavLink to="/callbacks">平台回调</NavLink>
          <NavLink to="/learn" className="learn-link">教学模式</NavLink>
        </nav>
        <div className="who">
          {session ? (<><span className="pill">{session.role}{session.platform ? ` · ${session.platform}` : ""}</span>
            <span className="muted">{session.sub}</span><button className="ghost" onClick={logout}>退出</button></>)
            : <NavLink to="/login">登录</NavLink>}
        </div>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Navigate to={session ? (isReviewer ? "/review" : "/cases") : "/learn"} />} />
          <Route path="/login" element={<Login onLogin={(s) => { set(s); nav(s.role === "platform" ? "/submit" : "/review"); }} />} />
          <Route path="/submit" element={<Submit />} />
          <Route path="/cases" element={<Cases />} />
          <Route path="/cases/:id" element={<CaseDetail />} />
          <Route path="/review" element={<ReviewQueue />} />
          <Route path="/review/:id" element={<ReviewCase />} />
          <Route path="/callbacks" element={<Callbacks />} />
          <Route path="/learn" element={<Learn />} />
          <Route path="/learn/interview" element={<Interview />} />
          <Route path="/learn/problems" element={<Problems />} />
        </Routes>
      </main>
    </div>
  );
}
