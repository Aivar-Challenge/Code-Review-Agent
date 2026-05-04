import React, { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, NavLink, useNavigate } from 'react-router-dom'
import Dashboard from './components/Dashboard'
import NewReview from './components/NewReview'
import RunDetail from './components/RunDetail'
import RunsList from './components/RunsList'
import ConfigPanel from './components/ConfigPanel'

function Sidebar() {
  const navItems = [
    { to: '/', icon: '🏠', label: 'Dashboard', end: true },
    { to: '/review/new', icon: '🔍', label: 'New Review' },
    { to: '/runs', icon: '📋', label: 'All Runs' },
    { to: '/config', icon: '⚙️', label: 'Config' },
  ]

  return (
    <aside className="app-sidebar">
      <div className="sidebar-logo">
        <h1><span className="logo-icon">🤖</span> CodeReview Agent</h1>
        <p>AI-powered PR analysis</p>
      </div>
      {navItems.map(item => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
        >
          <span className="nav-icon">{item.icon}</span>
          {item.label}
        </NavLink>
      ))}
    </aside>
  )
}

function Header() {
  const [time, setTime] = useState(new Date())

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  return (
    <header className="app-header">
      <div className="flex items-center gap-4">
        <span className="text-sm text-muted">
          GitHub Code Review Agent · v1.0
        </span>
      </div>
      <div className="flex items-center gap-4">
        <span className="text-xs font-mono text-muted">
          {time.toLocaleTimeString()}
        </span>
        <a
          href="http://localhost:8000/docs"
          target="_blank"
          rel="noopener noreferrer"
          className="btn btn-secondary btn-sm"
        >
          API Docs
        </a>
      </div>
    </header>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-layout">
        <Sidebar />
        <Header />
        <main className="app-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/review/new" element={<NewReview />} />
            <Route path="/runs" element={<RunsList />} />
            <Route path="/runs/:runId" element={<RunDetail />} />
            <Route path="/config" element={<ConfigPanel />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
