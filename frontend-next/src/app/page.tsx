"use client";

import React, { useState, useRef, useEffect } from 'react';
import styles from './page.module.css';
import { AskResponse, AskStreamEvent, ExecutionStep, Message, Session, HistoryMessage } from '../types';
import ChatBubble from '../components/ChatBubble';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function isExecutionStep(value: unknown): value is ExecutionStep {
  return (
    isRecord(value) &&
    typeof value.name === 'string' &&
    typeof value.status === 'string' &&
    typeof value.message === 'string' &&
    typeof value.elapsed_ms === 'number'
  );
}

function isAskResponse(value: unknown): value is AskResponse {
  return (
    isRecord(value) &&
    typeof value.query === 'string' &&
    typeof value.success === 'boolean' &&
    typeof value.execution_time_ms === 'number' &&
    Array.isArray(value.execution_steps)
  );
}

function parseStreamEvent(value: unknown): AskStreamEvent | null {
  if (!isRecord(value)) {
    return null;
  }

  if (
    (value.type === 'step_start' || value.type === 'step') &&
    isExecutionStep(value.data)
  ) {
    return { type: value.type, data: value.data };
  }

  if (value.type === 'result' && isAskResponse(value.data)) {
    return { type: 'result', data: value.data };
  }

  return null;
}

function generateUUID() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    const r = Math.random() * 16 | 0;
    const v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [sessionToDelete, setSessionToDelete] = useState<string | null>(null);
  const [sessionToRename, setSessionToRename] = useState<string | null>(null);
  const [renameTitle, setRenameTitle] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    fetchSessions();
  }, []);

  async function fetchSessions() {
    try {
      const res = await fetch('/api/history/sessions', { cache: 'no-store' });
      if (res.ok) {
        const data = await res.json();
        setSessions(data);
      }
    } catch (err) {
      console.error("Failed to fetch sessions", err);
    }
  };

  const loadSessionMessages = async (sessionId: string) => {
    if (sessionId === currentSessionId) return;
    setCurrentSessionId(sessionId);
    setMessages([]);
    setIsLoading(true);
    try {
      const res = await fetch(`/api/history/sessions/${sessionId}/messages`, { cache: 'no-store' });
      if (res.ok) {
        const data: HistoryMessage[] = await res.json();
        const loadedMessages: Message[] = data.map((msg, index) => {
          let content = msg.content;
          let responseObj = undefined;

          if (msg.role === 'assistant') {
            try {
              responseObj = JSON.parse(msg.content);
              content = responseObj.analysis || msg.content;
            } catch (e) {
              // Not JSON, just text
            }
          }

          return {
            id: `${sessionId}-${index}`,
            role: msg.role,
            content: content,
            response: responseObj,
            steps: [],
            status: 'success'
          };
        });
        setMessages(loadedMessages);
      }
    } catch (err) {
      console.error("Failed to load session messages", err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleNewChat = () => {
    setCurrentSessionId(null);
    setMessages([]);
    setQuery("");
  };

  const confirmDeleteSession = async () => {
    if (!sessionToDelete) return;
    setIsDeleting(true);
    try {
      const res = await fetch(`/api/history/sessions/${sessionToDelete}`, { method: 'DELETE' });
      if (res.ok) {
        if (currentSessionId === sessionToDelete) {
          handleNewChat();
        }
        await fetchSessions();
      }
    } catch (err) {
      console.error("Failed to delete session", err);
    } finally {
      setIsDeleting(false);
      setSessionToDelete(null);
    }
  };

  const handleDeleteSession = (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    setSessionToDelete(sessionId);
  };

  const handleStartRename = (e: React.MouseEvent, session: Session) => {
    e.stopPropagation();
    setSessionToRename(session.session_id);
    setRenameTitle(session.title || "新会话");
  };

  const submitRename = async (e?: React.FormEvent | React.MouseEvent) => {
    if (e) { e.preventDefault(); e.stopPropagation(); }
    if (!sessionToRename) return;
    try {
      const res = await fetch(`/api/history/sessions/${sessionToRename}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: renameTitle })
      });
      if (res.ok) {
        await fetchSessions();
      }
    } catch (err) {
      console.error("Failed to rename session", err);
    } finally {
      setSessionToRename(null);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || isLoading) return;

    let targetSessionId = currentSessionId;
    let isFirstQuery = false;
    if (!targetSessionId) {
      targetSessionId = generateUUID();
      setCurrentSessionId(targetSessionId);
      isFirstQuery = true;
    }

    const userMessage: Message = { id: Date.now().toString(), role: 'user', content: query, steps: [], status: 'success' };
    const assistantId = (Date.now() + 1).toString();
    const assistantMessage: Message = { id: assistantId, role: 'assistant', steps: [], status: 'pending' };

    setMessages(prev => [...prev, userMessage, assistantMessage]);
    setQuery("");
    setIsLoading(true);

    try {
      const response = await fetch('/api/ask/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: userMessage.content,
          thread_id: targetSessionId
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('响应体为空，无法读取流式结果');
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const eventData = parseStreamEvent(JSON.parse(line.substring(6)));

              if (eventData?.type === 'result') {
                setMessages(prev => prev.map(msg => {
                  if (msg.id === assistantId) {
                    return {
                      ...msg,
                      steps: eventData.data.execution_steps,
                      response: eventData.data,
                      status: eventData.data.success ? 'success' : 'error',
                      errorMessage: eventData.data.error_message
                    };
                  }
                  return msg;
                }));

                if (isFirstQuery) {
                  setTimeout(fetchSessions, 1000);
                }
              }
            } catch (err) {
              console.error("Failed to parse SSE event:", line, err);
            }
          }
        }
      }
    } catch (error: unknown) {
      console.error("Stream error:", error);
      const errorMessage = error instanceof Error ? error.message : '网络或解析错误';
      setMessages(prev => prev.map(msg => {
        if (msg.id === assistantId) {
          return { ...msg, status: 'error', errorMessage };
        }
        return msg;
      }));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className={styles.layoutWrapper}>
      {/* Sidebar */}
      <aside className={styles.sidebar}>
        <button className={styles.newChatBtn} onClick={handleNewChat}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19"></line>
            <line x1="5" y1="12" x2="19" y2="12"></line>
          </svg>
          新会话
        </button>
        <div className={styles.sessionList}>
          {sessions.map(session => (
            <div
              key={session.session_id}
              className={`${styles.sessionItemWrapper} ${currentSessionId === session.session_id ? styles.active : ''}`}
              onClick={() => loadSessionMessages(session.session_id)}
            >
              {sessionToRename === session.session_id ? (
                <form
                  onSubmit={submitRename}
                  style={{ width: '100%', display: 'flex', gap: '0.5rem' }}
                  onClick={e => e.stopPropagation()}
                >
                  <input
                    type="text"
                    className={styles.renameInput}
                    value={renameTitle}
                    onChange={(e) => setRenameTitle(e.target.value)}
                    autoFocus
                    onBlur={() => setSessionToRename(null)}
                  />
                </form>
              ) : (
                <>
                  <span className={styles.sessionItemTitle} title={session.title}>
                    {session.title || "新会话"}
                  </span>

                  <div style={{ display: 'flex', gap: '0.25rem' }}>
                    <button
                      className={styles.editBtn}
                      onClick={(e) => handleStartRename(e, session)}
                      title="重命名"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M12 20h9"></path>
                        <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path>
                      </svg>
                    </button>

                    <button
                      className={styles.deleteBtn}
                      onClick={(e) => handleDeleteSession(e, session.session_id)}
                      title="删除会话"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M3 6h18"></path>
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                      </svg>
                    </button>
                  </div>
                </>
              )}

              {sessionToDelete === session.session_id && (
                <div className={styles.popover} onClick={e => e.stopPropagation()}>
                  <div className={styles.popoverText}>确认删除?</div>
                  <div className={styles.popoverActions}>
                    <button className={styles.popoverBtn} onClick={(e) => { e.stopPropagation(); setSessionToDelete(null); }}>取消</button>
                    <button className={`${styles.popoverBtn} ${styles.popoverBtnDanger}`} onClick={(e) => { e.stopPropagation(); confirmDeleteSession(); }}>{isDeleting ? '...' : '删除'}</button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </aside>

      {/* Main Chat Area */}
      <main className={styles.container}>
        {/* Header */}
        <header className={styles.header}>
          <div className="glass-panel" style={{ padding: '1rem 2rem', display: 'inline-block', marginBottom: '1rem' }}>
            <h1 style={{ margin: 0, fontSize: '1.5rem', fontWeight: 600, color: 'var(--primary)' }}>
              AutoBI
            </h1>
            <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--text-muted)' }}>
              智能数据分析助手
            </p>
          </div>
        </header>

        {/* Chat Area */}
        <div className={styles.chatArea}>
          {messages.length === 0 ? (
            <div className={styles.welcomeMessage}>
              <h2>欢迎使用 AutoBI</h2>
              <p>请在下方输入您关心的数据指标，例如：“各品牌上月销量排名” 或 “新能源乘用车市场趋势”。</p>
            </div>
          ) : (
            messages.map(msg => <ChatBubble key={msg.id} message={msg} />)
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className={styles.inputArea}>
          <form onSubmit={handleSubmit} className={styles.inputForm}>
            <input
              type="text"
              className={styles.input}
              placeholder="输入您关心的数据问题..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              disabled={isLoading}
            />
            <button type="submit" className={styles.submitButton} disabled={isLoading || !query.trim()}>
              {isLoading ? '分析中...' : '发送'}
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}
