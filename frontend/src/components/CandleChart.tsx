import { useEffect, useRef } from 'react';
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
} from 'lightweight-charts';

type Props = {
  candles: any[];
  markers?: any[];
  source?: string;
};

export function CandleChart({ candles, markers = [], source }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<any> | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      layout: {
        background: { color: 'transparent' },
        textColor: '#8b9bb4',
      },
      grid: {
        vertLines: { color: 'rgba(36,48,68,0.45)' },
        horzLines: { color: 'rgba(36,48,68,0.45)' },
      },
      rightPriceScale: { borderColor: '#243044' },
      timeScale: { borderColor: '#243044', timeVisible: true },
      crosshair: { mode: 0 },
      height: ref.current.clientHeight || 400,
    });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#00c853',
      downColor: '#ff1744',
      borderVisible: false,
      wickUpColor: '#00c853',
      wickDownColor: '#ff1744',
    });
    const vol = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    });
    chart.priceScale('vol').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });
    chartRef.current = chart;
    seriesRef.current = series;
    volRef.current = vol;
    markersRef.current = createSeriesMarkers(series, []);

    const ro = new ResizeObserver(() => {
      if (ref.current) {
        chart.applyOptions({ height: ref.current.clientHeight, width: ref.current.clientWidth });
      }
    });
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      chart.remove();
    };
  }, []);

  useEffect(() => {
    if (!seriesRef.current || !volRef.current || !candles?.length) return;
    const data = candles.map((c) => ({
      time: c.time as any,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));
    const vols = candles.map((c) => ({
      time: c.time as any,
      value: c.volume,
      color: c.close >= c.open ? 'rgba(0,200,83,0.35)' : 'rgba(255,23,68,0.35)',
    }));
    seriesRef.current.setData(data);
    volRef.current.setData(vols);
    markersRef.current?.setMarkers((markers || []) as any);
    chartRef.current?.timeScale().fitContent();
  }, [candles, markers]);

  return (
    <div className="chart-wrap">
      {source && <div className="src-tag">{source} DATA</div>}
      <div ref={ref} style={{ width: '100%', height: '100%' }} />
    </div>
  );
}
