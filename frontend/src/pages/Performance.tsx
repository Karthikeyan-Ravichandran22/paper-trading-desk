import { useEffect, useState } from 'react';
import { api } from '../api';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar, PieChart, Pie, Cell } from 'recharts';

export function PerformancePage() {
  const [data, setData] = useState<any>(null);
  const [report, setReport] = useState<any>(null);
  const [exp, setExp] = useState<any>(null);

  useEffect(() => {
    api.performance().then(setData).catch(console.error);
    api.experiment().then(setExp).catch(console.error);
  }, []);

  async function loadReport() {
    const r = await api.experimentReport();
    setReport(r);
  }

  const m = data?.metrics || {};
  const colors = ['#00c853', '#ff1744', '#8b9bb4'];

  return (
    <div>
      <h1 className="page-title">Performance · PAPER TRADE</h1>
      <div className="metrics-row" style={{ marginBottom: 12 }}>
        <div className="metric"><div className="l">Total Trades</div><div className="v">{m.total_trades ?? 0}</div></div>
        <div className="metric"><div className="l">Win Rate</div><div className="v">{m.win_rate ?? 0}%</div></div>
        <div className="metric"><div className="l">Net Profit</div><div className={`v ${(m.net_profit || 0) >= 0 ? 'up' : 'down'}`}>₹{m.net_profit ?? 0}</div></div>
        <div className="metric"><div className="l">Profit Factor</div><div className="v">{m.profit_factor_infinite ? '∞' : (m.profit_factor ?? '—')}</div></div>
        <div className="metric"><div className="l">Max DD</div><div className="v">{m.maximum_drawdown_pct ?? 0}%</div></div>
        <div className="metric"><div className="l">Avg Trade</div><div className="v">₹{m.average_trade ?? 0}</div></div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 12 }}>
        <div className="panel">
          <div className="panel-h"><span>Equity Curve</span></div>
          <div className="panel-b" style={{ height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data?.equity_curve || []}>
                <XAxis dataKey="ts" hide />
                <YAxis domain={['auto', 'auto']} stroke="#8b9bb4" fontSize={11} />
                <Tooltip contentStyle={{ background: '#121a27', border: '1px solid #243044' }} />
                <Line type="monotone" dataKey="equity" stroke="#00e5ff" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="panel">
          <div className="panel-h"><span>Daily P&L</span></div>
          <div className="panel-b" style={{ height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data?.daily_pnl || []}>
                <XAxis dataKey="date" stroke="#8b9bb4" fontSize={10} />
                <YAxis stroke="#8b9bb4" fontSize={11} />
                <Tooltip contentStyle={{ background: '#121a27', border: '1px solid #243044' }} />
                <Bar dataKey="pnl" fill="#ffc400" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="panel">
          <div className="panel-h"><span>Trade Distribution</span></div>
          <div className="panel-b" style={{ height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={[
                    { name: 'Winning', value: data?.distribution?.winning || 0 },
                    { name: 'Losing', value: data?.distribution?.losing || 0 },
                    { name: 'Break-even', value: data?.distribution?.breakeven || 0 },
                  ]}
                  dataKey="value"
                  nameKey="name"
                  outerRadius={80}
                  label
                >
                  {colors.map((c, i) => <Cell key={i} fill={c} />)}
                </Pie>
                <Tooltip contentStyle={{ background: '#121a27', border: '1px solid #243044' }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 12 }}>
        <div className="panel-h">
          <span>7-DAY PAPER TEST</span>
          <button className="btn primary" onClick={loadReport}>Generate Snapshot Report</button>
        </div>
        <div className="panel-b">
          {exp && (
            <div className="kv" style={{ maxWidth: 480, marginBottom: 12 }}>
              <span>Status</span><span>{exp.status}</span>
              <span>Started</span><span>{exp.started_at}</span>
              <span>Ends</span><span>{exp.ends_at}</span>
              <span>Strategy</span><span>{exp.strategy}</span>
              <span>Capital</span><span>₹{exp.starting_capital?.toLocaleString('en-IN')}</span>
            </div>
          )}
          {report && (
            <div>
              <h3 style={{ marginTop: 0 }}>{report.title}</h3>
              <div className="metrics-row">
                <div className="metric"><div className="l">Starting</div><div className="v">₹{report.starting_capital}</div></div>
                <div className="metric"><div className="l">Ending</div><div className="v">₹{report.ending_capital}</div></div>
                <div className="metric"><div className="l">Net P&L</div><div className="v">₹{report.net_pnl}</div></div>
                <div className="metric"><div className="l">Return %</div><div className="v">{report.return_pct}%</div></div>
              </div>
              <p style={{ color: 'var(--muted)', fontSize: '0.8rem' }}>{report.disclaimer}</p>
              <pre style={{ fontSize: '0.72rem', overflow: 'auto', background: 'var(--bg-1)', padding: 12, borderRadius: 4 }}>
                {JSON.stringify({ strategy_performance: report.strategy_performance, simulated_execution_performance: report.simulated_execution_performance, signal_accuracy: report.signal_accuracy }, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
