import { Fragment, useEffect, useState } from 'react';
import { api } from '../api';

export function TradesPage() {
  const [trades, setTrades] = useState<any[]>([]);
  const [open, setOpen] = useState<number | null>(null);

  useEffect(() => {
    api.trades().then(setTrades);
    const id = setInterval(() => api.trades().then(setTrades), 5000);
    return () => clearInterval(id);
  }, []);

  return (
    <div>
      <h1 className="page-title">Trade History · PAPER</h1>
      <div className="panel">
        <div className="panel-b" style={{ padding: 0 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Time</th><th>Symbol</th><th>Side</th><th>Entry</th><th>Exit</th>
                <th>Qty</th><th>P&L</th><th>P&L %</th><th>Duration</th><th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t) => (
                <Fragment key={t.id}>
                  <tr onClick={() => setOpen(open === t.id ? null : t.id)} style={{ cursor: 'pointer' }}>
                    <td>{t.time}</td>
                    <td>{t.symbol}</td>
                    <td>{t.side}</td>
                    <td>{t.entry}</td>
                    <td>{t.exit}</td>
                    <td>{t.qty}</td>
                    <td className={t.pnl >= 0 ? 'up' : 'down'}>{t.pnl}</td>
                    <td>{t.pnl_pct}</td>
                    <td>{Math.round((t.duration_seconds || 0) / 60)}m</td>
                    <td>{t.reason}</td>
                  </tr>
                  {open === t.id && (
                    <tr>
                      <td colSpan={10} style={{ background: 'rgba(0,0,0,0.25)' }}>
                        <pre style={{ margin: 0, fontSize: '0.72rem', whiteSpace: 'pre-wrap' }}>
                          {JSON.stringify(t.expanded, null, 2)}
                        </pre>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
              {!trades.length && <tr><td colSpan={10} style={{ color: 'var(--muted)' }}>No paper trades yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export function SignalsPage() {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => {
    api.signals().then(setRows);
    const id = setInterval(() => api.signals().then(setRows), 4000);
    return () => clearInterval(id);
  }, []);
  return (
    <div>
      <h1 className="page-title">Signals</h1>
      <div className="panel">
        <div className="panel-b" style={{ padding: 0 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Time</th><th>Symbol</th><th>Signal</th><th>Price</th><th>SL</th><th>Target</th>
                <th>Acted</th><th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.id}>
                  <td>{s.time}</td>
                  <td>{s.symbol}</td>
                  <td className={s.signal === 'BUY' ? 'up' : s.signal === 'SELL' ? 'down' : ''}>{s.signal}</td>
                  <td>{s.price}</td>
                  <td>{s.stop_loss ?? '—'}</td>
                  <td>{s.target ?? '—'}</td>
                  <td>{s.acted_on ? 'Yes' : (s.rejection_reason || 'No')}</td>
                  <td style={{ maxWidth: 280 }}>{s.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export function OrdersPage() {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => {
    api.orders().then(setRows);
    const id = setInterval(() => api.orders().then(setRows), 4000);
    return () => clearInterval(id);
  }, []);
  return (
    <div>
      <h1 className="page-title">Paper Orders</h1>
      <div className="panel">
        <div className="panel-b" style={{ padding: 0 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Time</th><th>Symbol</th><th>Side</th><th>Qty</th><th>Fill</th>
                <th>Status</th><th>Broker</th><th>Mode</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((o) => (
                <tr key={o.id}>
                  <td>{o.time}</td>
                  <td>{o.symbol}</td>
                  <td>{o.side}</td>
                  <td>{o.qty}</td>
                  <td>{o.fill}</td>
                  <td>{o.status}</td>
                  <td>{o.broker}</td>
                  <td style={{ color: 'var(--paper)' }}>{o.mode}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export function PortfolioPage() {
  const [p, setP] = useState<any>(null);
  useEffect(() => {
    api.portfolio().then(setP);
    const id = setInterval(() => api.portfolio().then(setP), 4000);
    return () => clearInterval(id);
  }, []);
  if (!p) return null;
  const m = p.metrics || {};
  return (
    <div>
      <h1 className="page-title">Paper Portfolio</h1>
      <div className="metrics-row">
        {[
          ['Initial Capital', `₹${p.initial_capital?.toLocaleString('en-IN')}`],
          ['Current Equity', `₹${p.current_equity?.toLocaleString('en-IN')}`],
          ['Available Cash', `₹${p.available_cash?.toLocaleString('en-IN')}`],
          ['Invested', `₹${p.invested_capital?.toLocaleString('en-IN')}`],
          ['Realized P&L', `₹${p.realized_pnl}`],
          ['Unrealized P&L', `₹${p.unrealized_pnl}`],
          ['Total P&L', `₹${p.total_pnl}`],
          ['Return %', `${p.return_pct}%`],
          ['Max Drawdown', `${p.maximum_drawdown}%`],
          ['Win Rate', `${m.win_rate}%`],
          ['Trades', m.total_trades],
          ['Avg Win', `₹${m.average_win}`],
          ['Avg Loss', `₹${m.average_loss}`],
          ['Profit Factor', m.profit_factor_infinite ? '∞' : m.profit_factor],
          ['Largest Win', `₹${m.largest_win}`],
          ['Largest Loss', `₹${m.largest_loss}`],
        ].map(([l, v]) => (
          <div className="metric" key={String(l)}><div className="l">{l}</div><div className="v">{v}</div></div>
        ))}
      </div>
      <p style={{ color: 'var(--muted)', fontSize: '0.8rem', marginTop: 12 }}>{p.cost_assumptions?.disclaimer}</p>
    </div>
  );
}

export function SettingsPage() {
  const [totp, setTotp] = useState('');
  const [status, setStatus] = useState<any>(null);
  const [probe, setProbe] = useState<any>(null);
  const [port, setPort] = useState({ slippage_bps: 5, brokerage_per_order: 20, max_position_size: 50000, max_daily_loss: 5000, max_open_positions: 3 });
  const [msg, setMsg] = useState('');

  useEffect(() => {
    api.status().then(setStatus);
    api.portfolio().then((p) => setPort({
      slippage_bps: p.cost_assumptions.slippage_bps,
      brokerage_per_order: p.cost_assumptions.brokerage_per_order,
      max_position_size: p.settings.max_position_size,
      max_daily_loss: p.settings.max_daily_loss,
      max_open_positions: p.settings.max_open_positions,
    }));
  }, []);

  return (
    <div>
      <h1 className="page-title">Settings</h1>
      <div className="panel" style={{ marginBottom: 12 }}>
        <div className="panel-h"><span>Angel One Connection (server-side)</span></div>
        <div className="panel-b form-grid">
          <div style={{ color: 'var(--muted)', fontSize: '0.85rem' }}>
            Credentials are read from server environment variables only. Never enter API secret/password in the browser beyond TOTP for login session.
            Status: {status?.angel_one?.label || '—'}
          </div>
          <label>TOTP (optional login)
            <input value={totp} onChange={(e) => setTotp(e.target.value)} placeholder="6-digit TOTP" />
          </label>
          <button className="btn primary" onClick={async () => {
            const r: any = await api.angelLogin(totp);
            setMsg(r.message || JSON.stringify(r));
            setStatus(await api.status());
          }}>Connect Angel One</button>
          {msg && <div>{msg}</div>}
        </div>
      </div>

      <div className="panel" style={{ marginBottom: 12 }}>
        <div className="panel-h"><span>Paper Trading Assumptions</span></div>
        <div className="panel-b form-grid">
          {Object.entries(port).map(([k, v]) => (
            <label key={k}>{k}
              <input type="number" value={v} onChange={(e) => setPort({ ...port, [k]: Number(e.target.value) })} />
            </label>
          ))}
          <button className="btn" onClick={async () => {
            await api.updatePortfolio(port);
            setMsg('Portfolio settings updated');
          }}>Save</button>
        </div>
      </div>

      <div className="panel">
        <div className="panel-h"><span>Safety Probe</span></div>
        <div className="panel-b">
          <button className="btn danger" onClick={async () => setProbe(await api.probeLive())}>
            Prove live Angel One order API is blocked
          </button>
          {probe && (
            <pre style={{ marginTop: 12, fontSize: '0.75rem' }}>{JSON.stringify(probe, null, 2)}</pre>
          )}
        </div>
      </div>
    </div>
  );
}

export function LogsPage() {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => {
    api.audit().then(setRows);
    const id = setInterval(() => api.audit().then(setRows), 5000);
    return () => clearInterval(id);
  }, []);
  return (
    <div>
      <h1 className="page-title">System Logs / Audit</h1>
      <div className="panel">
        <div className="panel-b" style={{ padding: 0 }}>
          <table className="table">
            <thead>
              <tr><th>Time</th><th>Level</th><th>Category</th><th>Action</th><th>Symbol</th><th>Detail</th></tr>
            </thead>
            <tbody>
              {rows.map((a) => (
                <tr key={a.id}>
                  <td>{a.timestamp}</td>
                  <td>{a.level}</td>
                  <td>{a.category}</td>
                  <td>{a.action}</td>
                  <td>{a.symbol || '—'}</td>
                  <td style={{ maxWidth: 360, overflow: 'hidden', textOverflow: 'ellipsis' }}>{JSON.stringify(a.detail)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export function SystemPage() {
  const [s, setS] = useState<any>(null);
  useEffect(() => {
    const load = () => api.status().then(setS);
    load();
    const id = setInterval(load, 2000);
    return () => clearInterval(id);
  }, []);
  if (!s) return null;
  const items = [
    ['Angel One', s.angel_one?.label],
    ['Market Data', s.market_data?.data_status],
    ['Data Source', s.market_data?.source],
    ['WebSocket', s.websocket],
    ['Strategy', s.strategy?.status],
    ['Strategy Name', s.strategy?.name],
    ['Paper Engine', s.paper_engine],
    ['Live Trading', s.live_trading],
    ['Market', s.market_status?.status],
    ['Last Tick', s.last_tick],
    ['Last Strategy Eval', s.last_strategy_evaluation],
  ];
  return (
    <div>
      <h1 className="page-title">System Status</h1>
      <div className="status-grid">
        {items.map(([l, v]) => (
          <div className="metric" key={String(l)}>
            <div className="l">{l}</div>
            <div className="v" style={{ fontSize: '0.85rem' }}>{String(v ?? '—')}</div>
          </div>
        ))}
      </div>
      <p style={{ color: 'var(--amber)', marginTop: 16, fontSize: '0.85rem' }}>{s.data_source_note}</p>
      {s.market_data?.stale && s.market_data?.source !== 'DEMO' && (
        <div className="panel" style={{ marginTop: 12, borderColor: 'var(--red)' }}>
          <div className="panel-b" style={{ color: 'var(--red)' }}>
            MARKET DATA DISCONNECTED / STALE — strategy execution paused.
          </div>
        </div>
      )}
    </div>
  );
}

export function BacktestPage() {
  const [result, setResult] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  async function run() {
    setBusy(true);
    try {
      setResult(await api.backtest({ symbol: 'NIFTY', timeframe: '5m', bars: 300, quantity: 50 }));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <h1 className="page-title">Backtest <span style={{ color: 'var(--amber)' }}>BACKTEST</span></h1>
      <p style={{ color: 'var(--muted)', fontSize: '0.85rem' }}>
        Historical simulation only — results are NOT mixed with the live paper-trading account.
      </p>
      <button className="btn primary" disabled={busy} onClick={run}>{busy ? 'Running…' : 'Run SORE Scalper Backtest (NIFTY 5m)'}</button>
      {result && (
        <div className="panel" style={{ marginTop: 12 }}>
          <div className="panel-b">
            <div className="metrics-row">
              <div className="metric"><div className="l">Trades</div><div className="v">{result.total_trades}</div></div>
              <div className="metric"><div className="l">Win Rate</div><div className="v">{result.win_rate}%</div></div>
              <div className="metric"><div className="l">Net P&L</div><div className="v">₹{result.net_pnl}</div></div>
              <div className="metric"><div className="l">Max DD</div><div className="v">{result.maximum_drawdown_pct}%</div></div>
              <div className="metric"><div className="l">Profit Factor</div><div className="v">{result.profit_factor ?? '—'}</div></div>
            </div>
            <p style={{ color: 'var(--muted)', fontSize: '0.8rem' }}>{result.disclaimer}</p>
          </div>
        </div>
      )}
    </div>
  );
}

export function ChartsPage() {
  return <div><h1 className="page-title">Charts</h1><p style={{ color: 'var(--muted)' }}>Use Dashboard for the primary live chart. Select symbols from the watchlist.</p></div>;
}

export function WatchlistPage() {
  const [rows, setRows] = useState<any[]>([]);
  const [sym, setSym] = useState('CRUDEOIL');
  const [exch, setExch] = useState('MCX');
  const load = () => api.watchlist().then(setRows);
  useEffect(() => {
    load();
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, []);
  return (
    <div>
      <h1 className="page-title">Watchlist</h1>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <input value={sym} onChange={(e) => setSym(e.target.value.toUpperCase())} placeholder="CRUDEOIL" style={{ background: 'var(--bg-1)', border: '1px solid var(--border)', padding: '0.4rem 0.6rem', borderRadius: 4 }} />
        <select value={exch} onChange={(e) => setExch(e.target.value)} style={{ background: 'var(--bg-1)', border: '1px solid var(--border)', padding: '0.4rem 0.6rem', borderRadius: 4 }}>
          <option value="MCX">MCX</option>
          <option value="NSE">NSE</option>
          <option value="BSE">BSE</option>
          <option value="NFO">NFO</option>
        </select>
        <button className="btn primary" onClick={async () => { await api.addWatch(sym, exch); setSym(''); load(); }}>Add</button>
        <button className="btn" onClick={async () => { await api.addWatch('CRUDEOIL', 'MCX'); load(); }}>Add MCX CRUDEOIL</button>
      </div>
      <div className="panel">
        <div className="panel-b" style={{ padding: 0 }}>
          <table className="table">
            <thead><tr><th>Symbol</th><th>Exch</th><th>LTP</th><th>Change %</th><th>Volume</th><th>Signal</th><th>Position</th><th></th></tr></thead>
            <tbody>
              {rows.map((w) => (
                <tr key={`${w.exchange}-${w.symbol}`}>
                  <td>{w.symbol}</td>
                  <td>{w.exchange || '—'}</td>
                  <td>{w.ltp}</td>
                  <td className={(w.change_pct || 0) >= 0 ? 'up' : 'down'}>{w.change_pct}%</td>
                  <td>{w.volume}</td>
                  <td>{w.signal || '—'}</td>
                  <td>{w.position || '—'}</td>
                  <td><button className="btn" onClick={async () => { await api.removeWatch(w.symbol); load(); }}>Remove</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
