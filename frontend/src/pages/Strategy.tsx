import { useEffect, useState } from 'react';
import { api } from '../api';

export function StrategyPage() {
  const [strat, setStrat] = useState<any>(null);
  const [validation, setValidation] = useState<any>(null);
  const [msg, setMsg] = useState('');
  const [form, setForm] = useState({ name: '', pine_source: '', timeframe: '5m', symbols: '', activate: true });

  useEffect(() => {
    api.strategy().then((s) => {
      setStrat(s);
      setForm({
        name: s.name,
        pine_source: s.pine_source,
        timeframe: s.timeframe,
        symbols: (s.symbols || []).join(','),
        activate: s.is_active,
      });
    });
  }, []);

  async function validate() {
    const r = await api.validateStrategy({ pine_source: form.pine_source, parameters: strat?.parameters });
    setValidation(r);
  }

  async function save() {
    try {
      const r: any = await api.updateStrategy({
        name: form.name,
        pine_source: form.pine_source,
        timeframe: form.timeframe,
        symbols: form.symbols.split(',').map((s) => s.trim()).filter(Boolean),
        activate: form.activate,
      });
      setMsg(`Saved version ${r.version}`);
      const s = await api.strategy();
      setStrat(s);
    } catch (e: any) {
      setMsg(e.message);
    }
  }

  return (
    <div>
      <h1 className="page-title">Strategy · SORE Scalper Pro</h1>
      <div className="panel" style={{ marginBottom: 12 }}>
        <div className="panel-h">
          <span>Active Version {strat?.version}</span>
          <span className={strat?.is_active ? 'up' : 'down'}>{strat?.is_active ? 'ACTIVE' : 'INACTIVE'}</span>
        </div>
        <div className="panel-b form-grid">
          <label>Strategy name
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </label>
          <label>Timeframe
            <select value={form.timeframe} onChange={(e) => setForm({ ...form, timeframe: e.target.value })}>
              {['1m', '3m', '5m', '15m', '30m'].map((t) => <option key={t}>{t}</option>)}
            </select>
          </label>
          <label>Symbols (comma-separated)
            <input value={form.symbols} onChange={(e) => setForm({ ...form, symbols: e.target.value })} />
          </label>
          <label>Pine Script
            <textarea value={form.pine_source} onChange={(e) => setForm({ ...form, pine_source: e.target.value })} />
          </label>
          <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input type="checkbox" checked={form.activate} onChange={(e) => setForm({ ...form, activate: e.target.checked })} />
            Activate after validation
          </label>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn" onClick={validate}>Validate</button>
            <button className="btn primary" onClick={save}>Save Strategy</button>
          </div>
          {msg && <div style={{ color: 'var(--amber)' }}>{msg}</div>}
        </div>
      </div>

      {(validation || strat?.validation_report) && (
        <div className="panel">
          <div className="panel-h"><span>STRATEGY VALIDATION</span></div>
          <div className="panel-b check-list">
            {Object.entries((validation?.checks || strat?.validation_report?.checks || {})).map(([k, v]) => (
              <div key={k}><span style={{ color: 'var(--muted)' }}>{k}:</span> {String(v)}</div>
            ))}
            <div style={{ marginTop: 12, color: 'var(--amber)' }}>Unsupported / disclosed features:</div>
            {(validation?.unsupported || strat?.unsupported_features || []).map((u: string, i: number) => (
              <div key={i}>• {u}</div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
