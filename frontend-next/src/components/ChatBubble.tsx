"use client";

import React from 'react';
import { Message, QueryCell } from '../types';
import Charts from './Charts';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Loader2 } from 'lucide-react';

function formatCell(cell: QueryCell): string {
  return cell === null ? '' : String(cell);
}

export default function ChatBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user';

  // Removed early return to show loading state

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'stretch', width: '100%', minWidth: 0, marginBottom: '2rem' }}>
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: isUser ? 'flex-end' : 'stretch',
          maxWidth: '100%',
          width: '100%',
          minWidth: 0,
        }}
      >
        <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.5rem', paddingLeft: '0.5rem', paddingRight: '0.5rem', textAlign: isUser ? 'right' : 'left' }}>
          {isUser ? '你' : 'AutoBI'}
        </div>

        {isUser ? (
          <div style={{
            backgroundColor: 'var(--primary)',
            color: 'white',
            padding: '1rem 1.5rem',
            borderRadius: '1.5rem 1.5rem 0 1.5rem',
            boxShadow: 'var(--shadow-sm)',
            maxWidth: '80%',
            overflowWrap: 'anywhere',
          }}>
            {message.content}
          </div>
        ) : (
          <div style={{ width: '100%' }}>
            {/* Simple Loading State */}
            {message.status === 'pending' && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '1.5rem', backgroundColor: '#f8fafc', padding: '1rem', borderRadius: 'var(--radius-lg)', border: '1px solid var(--border)' }}>
                <Loader2 size={16} color="var(--primary)" style={{ animation: 'spin 1s linear infinite' }} />
                正在启动分析链路
                <style>{`
                  @keyframes spin {
                    from { transform: rotate(0deg); }
                    to { transform: rotate(360deg); }
                  }
                `}</style>
              </div>
            )}

            {/* Error Message */}
            {message.status === 'error' && (
              <div style={{ backgroundColor: '#fef2f2', color: 'var(--error)', padding: '1rem', borderRadius: 'var(--radius-lg)', border: '1px solid #fca5a5', marginBottom: '1rem' }}>
                <span style={{ fontWeight: 600 }}>请求失败: </span>
                {message.errorMessage}
              </div>
            )}

            {/* SQL Snippet */}
            {message.response?.sql && (
              <div style={{ backgroundColor: '#1e293b', borderRadius: 'var(--radius-lg)', padding: '1rem', marginBottom: '1rem', overflowX: 'auto', boxShadow: 'var(--shadow-sm)' }}>
                <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Generated SQL</div>
                <pre style={{ margin: 0, color: '#f8fafc', fontSize: '0.875rem', fontFamily: 'var(--font-mono)' }}>
                  <code>{message.response.sql}</code>
                </pre>
              </div>
            )}

            {/* Chart */}
            {message.response?.chart_suggestion && message.response?.result && (
              <Charts suggestion={message.response.chart_suggestion} result={message.response.result} />
            )}

            {/* Result Table */}
            {message.response?.result && (
              <div style={{ overflowX: 'auto', backgroundColor: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', marginBottom: '1rem' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                  <thead>
                    <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid var(--border)' }}>
                      {message.response.result.columns.map((col, i) => (
                        <th key={i} style={{ padding: '0.75rem 1rem', textAlign: 'left', fontWeight: 600, color: 'var(--text-muted)' }}>{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {message.response.result.rows.map((row, i) => (
                      <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                        {row.map((cell: QueryCell, j: number) => (
                          <td key={j} style={{ padding: '0.75rem 1rem' }}>{formatCell(cell)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {message.response && (
              <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', marginBottom: '1rem' }}>
                执行耗时：{Math.round(message.response.execution_time_ms)}ms
              </div>
            )}

            {/* AI Analysis or Historical Content */}
            {(message.response?.analysis || (!message.response && message.content)) && (
              <div className="markdown-body" style={{ marginTop: '1rem', color: 'var(--foreground)', lineHeight: 1.6, fontSize: '0.875rem' }}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {message.response?.analysis || message.content || ''}
                </ReactMarkdown>
              </div>
            )}

          </div>
        )}
      </div>
    </div>
  );
}
