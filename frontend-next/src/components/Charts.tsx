"use client";

import React, { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import ReactECharts from 'echarts-for-react';
import { ChartSuggestion, QueryCell, QueryResult } from '../types';

interface ChartsProps {
  suggestion: ChartSuggestion;
  result: QueryResult;
}

const colors = ['#2563eb', '#16a34a', '#f59e0b', '#dc2626', '#7c3aed'];

function formatValue(value: QueryCell): string {
  if (value === null) {
    return '';
  }
  if (typeof value === 'number') {
    return value.toLocaleString('zh-CN');
  }
  return String(value);
}

function toNumber(value: QueryCell | undefined): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === 'string') {
    const parsed = Number(value.replaceAll(',', ''));
    return Number.isFinite(parsed) ? parsed : null;
  }

  return null;
}

function columnIndex(columns: string[], column?: string | null): number {
  return column ? columns.indexOf(column) : -1;
}

function validYAxes(columns: string[], yAxes?: string[] | null): string[] {
  return (yAxes ?? []).filter((column) => columns.includes(column));
}

function buildCartesianOption(
  chartType: 'bar' | 'line' | 'stacked_bar',
  title: string,
  columns: string[],
  rows: QueryCell[][],
  xIndex: number,
  yFields: string[],
): EChartsOption {
  const xAxisData = rows.map((row) => formatValue(row[xIndex] ?? null));
  const isLine = chartType === 'line';

  return {
    color: colors,
    title: {
      text: title,
      left: 'center',
      textStyle: {
        fontSize: 16,
        fontWeight: 600,
        color: '#0f172a',
      },
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(255, 255, 255, 0.95)',
      borderColor: '#e2e8f0',
      textStyle: { color: '#0f172a' },
    },
    legend: {
      bottom: 0,
      type: 'scroll',
      textStyle: { color: '#64748b' },
    },
    grid: { left: '3%', right: '4%', bottom: '12%', top: 50, containLabel: true },
    xAxis: {
      type: 'category',
      data: xAxisData,
      axisLine: { lineStyle: { color: '#cbd5e1' } },
      axisLabel: { color: '#64748b' },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#f1f5f9', type: 'dashed' } },
      axisLabel: { color: '#64748b' },
    },
    series: yFields.map((field) => {
      const yIndex = columns.indexOf(field);
      return {
        name: field,
        type: isLine ? 'line' : 'bar',
        stack: chartType === 'stacked_bar' ? 'total' : undefined,
        data: rows.map((row) => toNumber(row[yIndex]) ?? 0),
        smooth: isLine,
        symbol: isLine ? 'circle' : undefined,
        symbolSize: isLine ? 8 : undefined,
        lineStyle: isLine ? { width: 3 } : undefined,
        barMaxWidth: isLine ? undefined : 50,
        itemStyle: isLine ? undefined : { borderRadius: chartType === 'stacked_bar' ? 0 : [4, 4, 0, 0] },
      };
    }),
  };
}

function buildPieOption(
  title: string,
  rows: QueryCell[][],
  xIndex: number,
  yIndex: number,
  yField: string,
  customData?: { name: string; value: number }[]
): EChartsOption {
  return {
    color: colors,
    title: {
      text: title,
      left: 'center',
      textStyle: {
        fontSize: 16,
        fontWeight: 600,
        color: '#0f172a',
      },
    },
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(255, 255, 255, 0.95)',
      borderColor: '#e2e8f0',
      textStyle: { color: '#0f172a' },
    },
    series: [
      {
        name: yField,
        type: 'pie',
        radius: ['40%', '70%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 8,
          borderColor: '#fff',
          borderWidth: 2,
        },
        label: { show: false, position: 'center' },
        emphasis: {
          label: { show: true, fontSize: 16, fontWeight: 'bold' },
        },
        labelLine: { show: false },
        data: customData || rows.map((row) => ({
          name: formatValue(row[xIndex] ?? null),
          value: toNumber(row[yIndex]) ?? 0,
        })),
      },
    ],
  };
}

export default function Charts({ suggestion, result }: ChartsProps) {
  const title = suggestion.title ?? '数据图表';

  const metric = useMemo(() => {
    if (suggestion.chart_type !== 'metric' || result.rows.length === 0) {
      return null;
    }

    const yFields = validYAxes(result.columns, suggestion.y_axes);
    const valueIndex = yFields.length > 0 ? result.columns.indexOf(yFields[0]) : 0;
    const label = result.columns[valueIndex] ?? '指标';
    const value = result.rows[0]?.[valueIndex] ?? null;

    return { label, value };
  }, [result, suggestion]);

  const options = useMemo(() => {
    if (suggestion.chart_type === 'metric' || result.rows.length === 0) {
      return null;
    }

    const xIndex = columnIndex(result.columns, suggestion.x_axis);
    const yFields = validYAxes(result.columns, suggestion.y_axes);

    if (yFields.length === 0) {
      return null;
    }

    if (xIndex === -1) {
      if (suggestion.chart_type === 'pie' && result.rows.length === 1 && yFields.length > 1) {
        return buildPieOption(
          title,
          result.rows,
          -1,
          -1,
          '指标',
          yFields.map(field => ({ name: field, value: toNumber(result.rows[0][result.columns.indexOf(field)]) ?? 0 }))
        );
      }
      return null;
    }

    if (suggestion.chart_type === 'pie') {
      const yField = yFields[0];
      return buildPieOption(
        title,
        result.rows,
        xIndex,
        result.columns.indexOf(yField),
        yField,
      );
    }

    return buildCartesianOption(
      suggestion.chart_type,
      title,
      result.columns,
      result.rows,
      xIndex,
      yFields,
    );
  }, [result, suggestion, title]);

  if (metric) {
    return (
      <div style={{ backgroundColor: '#ffffff', padding: '1.5rem', borderRadius: 'var(--radius-lg)', boxShadow: 'var(--shadow-sm)', border: '1px solid var(--border)', marginTop: '1rem' }}>
        <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>{metric.label}</div>
        <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--foreground)' }}>{formatValue(metric.value)}</div>
        <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>{title}</div>
      </div>
    );
  }

  if (!options) return null;

  return (
    <div style={{ backgroundColor: '#ffffff', padding: '1.5rem', borderRadius: 'var(--radius-lg)', boxShadow: 'var(--shadow-sm)', border: '1px solid var(--border)', marginTop: '1rem' }}>
      <ReactECharts option={options} style={{ height: '350px', width: '100%' }} />
    </div>
  );
}
