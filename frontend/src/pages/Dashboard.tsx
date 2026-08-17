import { useEffect, useState } from 'react';
import { api } from '../api';
import { CandleChart } from '../components/CandleChart';

function fmt(n?: number | null, d = 2) {
  if (n == null || Number.isNaN(n)) return '—';
  return n.toLocaleString('en-IN', { maximumFractionDigits: d });
}

export function Dashboard() {
  const [status, setStatus] = useState<any>(null);
  const [watch, setWatch] = useState<any[]>([]);
  const [symbol, setSymbol] = useState('NIFTY');
  const [tf, setTf] = useState('5m');
  const [chart, setChart] = useState<any>(null);
  const [signal, setSignal] = useState<any>(null);
  const [positions, setPositions] = useState<any[]>([]);
  const [portfolio, setPortfolio] = useState<any>(null);
  const [trades, setTrades] = useState<any[]>([]);
  const [toasts, setToasts] = useState<any[]>([]);
  const [features, setFeatures] = useState<any>(null);

  async function refresh() {
    const [st, wl, sig, pos, port, tr, notes, candles, feat] = await Promise.all([
      api.status(),
      api.watchlist(),
      api.currentSignal(),
      api.positions(),
      api.portfolio(),
      api.trades(),
      api.notifications(),
      api.candles(symbol, tf),
      api.features(symbol, tf).catch(() => null),
    ]);
    setStatus(st);
    setWatch(wl);
    setSignal(sig);
    setPositions(pos);
    setPortfolio(port);
    setTrades(tr.slice(0, 8));
    setChart(candles);
    setFeatures(feat);
    if (notes?.length) {
      setToasts((prev) => [...notes.slice(-3), ...prev].slice(0, 5));
    }
  }

  useEffect(() => {
    refresh().catch(console.error);
    const id = setInterval(() => refresh().catch(() => {}), 3000);
    return () => clearInterval(id);
  }, [symbol, tf]);

  const pos = positions.find((p) => p.symbol === symbol) || positions[0];
  const mkt = status?.market_status?.status || '—';
  const dataLive = status?.market_data?.data_status || '—';

  return (
    <>
      <div className="toast-stack">
        {toasts.map((t, i) => (
          <div key={i} className={`toast ${t.type || ''}`}>
            <div className="t">{t.title || `NEW ${t.type} SIGNAL`}</div>
            <div>{t.symbol} · ₹{fmt(t.price)}</div>
            <div style={{ color: 'var(--muted)', marginTop: 4 }}>
              {t.timeframe} · PAPER · {t.order?.status || 'SIGNAL'}
            </div>
          </div>
        ))}
      </div>

      <div className="dashboard-grid">
        <div className="panel" style={{ gridRow: '1 / 2' }}>
          <div className="panel-h">
            <span>Watchlist</span>
            <select value={tf} onChange={(e) => setTf(e.target.value)} style={{ background: 'transparent', border: 'none' }}>
              {['1m', '3m', '5m', '15m', '30m'].map((x) => (
                <option key={x} value={x}>{x}</option>
              ))}
            </select>
          </div>
          <div className="panel-b" style={{ padding: 0 }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Sym</th>
                  <th>LTP</th>
                  <th>%</th>
                  <th>Sig</th>
                </tr>
              </thead>
              <tbody>
                {watch.map((w) => (
                  <tr key={w.symbol} onClick={() => setSymbol(w.symbol)} style={{ cursor: 'pointer', background: w.symbol === symbol ? 'rgba(0,229,255,0.06)' : undefined }}>
                    <td>{w.symbol}</td>
                    <td>{fmt(w.ltp)}</td>
                    <td className={(w.change_pct || 0) >= 0 ? 'up' : 'down'}>{fmt(w.change_pct)}%</td>
                    <td className={w.signal === 'BUY' ? 'up' : w.signal === 'SELL' ? 'down' : ''}>{w.signal || w.position || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="panel" style={{ gridRow: '1 / 2' }}>
          <div className="panel-h">
            <span>{symbol} · {tf} Candlestick</span>
            <span style={{ color: 'var(--paper)' }}>PAPER TRADING</span>
          </div>
          <div className="panel-b" style={{ padding: 0 }}>
            <CandleChart candles={chart?.candles || []} markers={chart?.markers || []} source={chart?.source} />
          </div>
        </div>

        <div className="panel" style={{ gridRow: '1 / 2' }}>
          <div className="panel-h"><span>Live Strategy</span></div>
          <div className="panel-b">
            <div className="signal-box">
              <div style={{ fontSize: '0.7rem', color: 'var(--muted)', letterSpacing: '0.1em' }}>CURRENT SIGNAL</div>
              <div className={`sig ${signal?.signal || 'HOLD'}`}>{signal?.signal || 'HOLD'}</div>
              <div className="kv">
                <span>Symbol</span><span>{signal?.symbol || symbol}</span>
                <span>Entry</span><span>₹{fmt(signal?.price)}</span>
                <span>Stop Loss</span><span>₹{fmt(signal?.stop_loss)}</span>
                <span>Target</span><span>₹{fmt(signal?.target)}</span>
                <span>TP2</span><span>₹{fmt(signal?.target2)}</span>
                <span>Quantity</span><span>{signal?.quantity ?? '—'}</span>
                <span>Signal Time</span><span>{(signal?.time || '').slice(11, 19) || '—'}</span>
              </div>
              {signal?.reason && (
                <div style={{ marginTop: 10, fontSize: '0.72rem', color: 'var(--muted)', textAlign: 'left' }}>
                  {signal.reason}
                </div>
              )}
            </div>
            <div style={{ borderTop: '1px solid var(--border)', margin: '0.5rem 0', paddingTop: '0.6rem' }}>
              <div style={{ fontSize: '0.7rem', color: 'var(--muted)', letterSpacing: '0.1em' }}>CURRENT POSITION</div>
              {pos ? (
                <div className="kv">
                  <span>Position</span><span className={pos.side === 'LONG' ? 'up' : 'down'}>{pos.side}</span>
                  <span>Entry</span><span>₹{fmt(pos.entry)}</span>
                  <span>LTP</span><span>₹{fmt(pos.ltp)}</span>
                  <span>Unrealized P&L</span>
                  <span className={pos.unrealized_pnl >= 0 ? 'up' : 'down'}>
                    {pos.unrealized_pnl >= 0 ? '+' : ''}₹{fmt(pos.unrealized_pnl)}
                  </span>
                </div>
              ) : (
                <div style={{ color: 'var(--muted)', fontSize: '0.85rem', marginTop: 8 }}>FLAT — no open position</div>
              )}
            </div>
            <div style={{ borderTop: '1px solid var(--border)', margin: '0.5rem 0', paddingTop: '0.6rem' }}>
              <div style={{ fontSize: '0.7rem', color: 'var(--muted)', letterSpacing: '0.1em' }}>
                CHART FEATURES · {features?.status || '—'}
              </div>
              <div className="kv">
                <span>Mode</span><span>{features?.mode || '—'}</span>
                <span>Trend</span><span>{features?.trend || '—'}</span>
                <span>MTF Gate</span><span>{features?.mtf_gate || '—'}</span>
                <span>Vol Mult</span><span>{features?.volatility_mult != null ? `${features.volatility_mult}x` : '—'}</span>
                <span>Entry</span><span>₹{fmt(features?.entry)}</span>
                <span>Stop-Loss</span><span>₹{fmt(features?.stop_loss)}</span>
                <span>TP1</span><span>₹{fmt(features?.tp1)}</span>
                <span>TP2</span><span>₹{fmt(features?.tp2)}</span>
              </div>
              {features?.reason && (
                <div style={{ marginTop: 8, fontSize: '0.72rem', color: 'var(--muted)' }}>{features.reason}</div>
              )}
            </div>
          </div>
        </div>

        <div className="panel" style={{ gridColumn: '1 / -1' }}>
          <div className="panel-h">
            <span>Paper Portfolio</span>
            <span>
              {status?.strategy?.name || 'Strategy'} · Market {mkt} · Data {dataLive}
            </span>
          </div>
          <div className="panel-b">
            <div className="metrics-row">
              <div className="metric"><div className="l">Capital</div><div className="v">₹{fmt(portfolio?.initial_capital, 0)}</div></div>
              <div className="metric"><div className="l">Equity</div><div className="v">₹{fmt(portfolio?.current_equity, 0)}</div></div>
              <div className="metric"><div className="l">Total P&L</div><div className={`v ${(portfolio?.total_pnl || 0) >= 0 ? 'up' : 'down'}`}>₹{fmt(portfolio?.total_pnl)}</div></div>
              <div className="metric"><div className="l">Win Rate</div><div className="v">{fmt(portfolio?.metrics?.win_rate)}%</div></div>
              <div className="metric"><div className="l">Drawdown</div><div className="v">{fmt(portfolio?.maximum_drawdown)}%</div></div>
              <div className="metric"><div className="l">Open Pos</div><div className="v">{positions.length}</div></div>
            </div>
            {portfolio?.cost_assumptions && (
              <div style={{ marginTop: 8, fontSize: '0.7rem', color: 'var(--muted)' }}>
                Costs (simulated): slippage {portfolio.cost_assumptions.slippage_bps} bps · brokerage ₹{portfolio.cost_assumptions.brokerage_per_order}/order — {portfolio.cost_assumptions.disclaimer}
              </div>
            )}
          </div>
        </div>

        <div className="panel" style={{ gridColumn: '1 / -1' }}>
          <div className="panel-h"><span>Recent Paper Trades</span></div>
          <div className="panel-b" style={{ padding: 0 }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Time</th><th>Symbol</th><th>Side</th><th>Entry</th><th>Exit</th><th>Qty</th><th>P&L</th><th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {trades.length === 0 && (
                  <tr><td colSpan={8} style={{ color: 'var(--muted)' }}>No closed paper trades yet — signals will populate this as the strategy runs.</td></tr>
                )}
                {trades.map((t) => (
                  <tr key={t.id}>
                    <td>{t.time}</td>
                    <td>{t.symbol}</td>
                    <td>{t.side}</td>
                    <td>{fmt(t.entry)}</td>
                    <td>{fmt(t.exit)}</td>
                    <td>{t.qty}</td>
                    <td className={t.pnl >= 0 ? 'up' : 'down'}>{fmt(t.pnl)}</td>
                    <td style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis' }}>{t.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
