const API = import.meta.env.VITE_API_URL || '';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail || err));
  }
  return res.json();
}

export const api = {
  status: () => request<any>('/api/status'),
  mode: () => request<any>('/api/mode'),
  watchlist: () => request<any[]>('/api/watchlist'),
  addWatch: (symbol: string, exchange = 'NSE') =>
    request('/api/watchlist', { method: 'POST', body: JSON.stringify({ symbol, exchange }) }),
  removeWatch: (symbol: string) => request(`/api/watchlist/${symbol}`, { method: 'DELETE' }),
  candles: (symbol: string, timeframe = '5m') => request<any>(`/api/candles/${symbol}?timeframe=${timeframe}&limit=200`),
  signals: () => request<any[]>('/api/signals'),
  currentSignal: () => request<any>('/api/signals/current'),
  notifications: () => request<any[]>('/api/notifications'),
  portfolio: () => request<any>('/api/portfolio'),
  positions: () => request<any[]>('/api/positions'),
  orders: () => request<any[]>('/api/orders'),
  trades: () => request<any[]>('/api/trades'),
  performance: () => request<any>('/api/performance'),
  strategy: () => request<any>('/api/strategy'),
  updateStrategy: (body: any) => request('/api/strategy', { method: 'PUT', body: JSON.stringify(body) }),
  validateStrategy: (body: any) => request('/api/strategy/validate', { method: 'POST', body: JSON.stringify(body) }),
  experiment: () => request<any>('/api/experiment'),
  experimentReport: () => request<any>('/api/experiment/report', { method: 'POST' }),
  backtest: (body: any) => request('/api/backtest', { method: 'POST', body: JSON.stringify(body) }),
  audit: () => request<any[]>('/api/audit'),
  angelLogin: (totp: string) => request('/api/angel/login', { method: 'POST', body: JSON.stringify({ totp }) }),
  probeLive: () => request<any>('/api/safety/probe-live-order', { method: 'POST' }),
  updatePortfolio: (body: any) => request('/api/portfolio/settings', { method: 'PATCH', body: JSON.stringify(body) }),
  features: (symbol = 'CRUDEOIL', timeframe = '5m') =>
    request<any>(`/api/features/current?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}`),
};

export function wsUrl() {
  const base = import.meta.env.VITE_WS_URL;
  if (base) return base;
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${location.host}/ws/live`;
}
