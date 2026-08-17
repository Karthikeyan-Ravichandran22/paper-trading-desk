import { NavLink, Route, Routes } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { api } from './api';
import { Dashboard } from './pages/Dashboard';
import { PerformancePage } from './pages/Performance';
import { StrategyPage } from './pages/Strategy';
import {
  BacktestPage,
  ChartsPage,
  LogsPage,
  OrdersPage,
  PortfolioPage,
  SettingsPage,
  SignalsPage,
  SystemPage,
  TradesPage,
  WatchlistPage,
} from './pages/MorePages';
import './styles.css';

const NAV = [
  ['/', 'Dashboard'],
  ['/watchlist', 'Watchlist'],
  ['/charts', 'Charts'],
  ['/signals', 'Signals'],
  ['/portfolio', 'Paper Portfolio'],
  ['/orders', 'Orders'],
  ['/trades', 'Trade History'],
  ['/performance', 'Performance'],
  ['/strategy', 'Strategy'],
  ['/backtest', 'Backtest'],
  ['/settings', 'Settings'],
  ['/system', 'System Status'],
  ['/logs', 'System Logs'],
] as const;

export default function App() {
  const [status, setStatus] = useState<any>(null);

  useEffect(() => {
    const load = () => api.status().then(setStatus).catch(() => {});
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  const angel = status?.angel_one?.connected
    ? 'Angel One Connected'
    : status?.angel_one?.configured
      ? 'Angel One Configured'
      : 'Angel One Demo Mode';
  const mkt = status?.market_status?.status || '—';
  const data = status?.market_data?.data_status || '—';

  return (
    <div className="app-shell">
      <div className="paper-banner">PAPER TRADING — NO REAL ORDERS · LIVE MODE DISABLED</div>
      <header className="topbar">
        <div className="brand">SORE Scalper · Paper Desk</div>
        <span className="pill warn">PAPER TRADING</span>
        <span className={`pill ${status?.angel_one?.connected ? 'ok' : 'warn'}`}>{angel}</span>
        <span className={`pill ${mkt === 'OPEN' ? 'live' : ''}`}>Market {mkt}</span>
        <span className={`pill ${data === 'LIVE' ? 'live' : ''}`}>Data {data}</span>
        <span className="pill">Strategy: {status?.strategy?.name || '—'}</span>
        <span className="pill">TF: {status?.strategy?.timeframe || '5m'}</span>
        <div className="mode-badge">PAPER MODE</div>
      </header>

      <div className="layout">
        <nav className="nav">
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => (isActive ? 'active' : '')}>
              {label}
            </NavLink>
          ))}
        </nav>
        <main className="content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/watchlist" element={<WatchlistPage />} />
            <Route path="/charts" element={<ChartsPage />} />
            <Route path="/signals" element={<SignalsPage />} />
            <Route path="/portfolio" element={<PortfolioPage />} />
            <Route path="/orders" element={<OrdersPage />} />
            <Route path="/trades" element={<TradesPage />} />
            <Route path="/performance" element={<PerformancePage />} />
            <Route path="/strategy" element={<StrategyPage />} />
            <Route path="/backtest" element={<BacktestPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/system" element={<SystemPage />} />
            <Route path="/logs" element={<LogsPage />} />
          </Routes>
        </main>
      </div>

      <nav className="mobile-nav">
        <NavLink to="/" end>Dashboard</NavLink>
        <NavLink to="/charts">Charts</NavLink>
        <NavLink to="/signals">Signals</NavLink>
        <NavLink to="/portfolio">Portfolio</NavLink>
        <NavLink to="/settings">More</NavLink>
      </nav>
    </div>
  );
}
