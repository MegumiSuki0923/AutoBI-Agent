"use client";
import React from 'react';
import { ExecutionStep } from '../types';
import { CheckCircle2, XCircle, Loader2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

export default function ExecutionSteps({ steps, status }: { steps: ExecutionStep[], status: string }) {
  // Translate internal node names to user-friendly labels
  const nodeLabels: Record<string, string> = {
    'intent_check': '意图识别',
    'daily_qa': '日常问答',
    'retrieve_context': '检索数据字典',
    'generate_sql': '生成 SQL',
    'guard_sql': 'SQL 安全校验',
    'execute_sql': '查询 Doris 数仓',
    'recommend_chart': '推荐可视化图表',
    'generate_analysis': '生成分析结论',
    'record_success': '保存记录',
    'record_failure': '记录失败',
    'build_response': '生成结果',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', width: '100%', minWidth: 0, marginBottom: '1.5rem', backgroundColor: '#f8fafc', padding: '1rem', borderRadius: 'var(--radius-lg)', border: '1px solid var(--border)' }}>
      {steps.length === 0 && status === 'pending' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
          <Loader2 size={16} color="var(--primary)" style={{ animation: 'spin 1s linear infinite' }} />
          正在启动分析链路
        </div>
      )}
      <AnimatePresence>
        {steps.map((step, idx) => {
          const isFailed = step.status === 'failed';
          const isRunning = step.status === 'running';

          return (
            <motion.div
              key={idx}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem', fontSize: '0.875rem' }}
            >
              <div style={{ marginTop: '0.125rem' }}>
                {isFailed ? (
                  <XCircle size={16} color="var(--error)" />
                ) : isRunning ? (
                  <Loader2 size={16} color="var(--primary)" className="animate-spin" style={{ animation: 'spin 1s linear infinite' }} />
                ) : (
                  <CheckCircle2 size={16} color="var(--success)" />
                )}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 500, color: 'var(--foreground)' }}>
                  {nodeLabels[step.name] || step.name}
                  {!isRunning && (
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginLeft: '0.5rem', fontWeight: 400 }}>
                      {step.elapsed_ms}ms
                    </span>
                  )}
                </div>
                <div style={{ color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                  {step.message}
                </div>
              </div>
            </motion.div>
          );
        })}
      </AnimatePresence>
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
