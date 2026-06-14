export type QueryCell = string | number | boolean | null;

export interface ExecutionStep {
  name: string;
  status: string;
  message: string;
  elapsed_ms: number;
}

export interface QueryResult {
  columns: string[];
  rows: QueryCell[][];
}

export type ChartType = 'line' | 'bar' | 'stacked_bar' | 'pie' | 'metric';

export interface ChartSuggestion {
  chart_type: ChartType;
  title?: string | null;
  x_axis?: string | null;
  y_axes?: string[] | null;
}

export interface AskResponse {
  query: string;
  sql?: string;
  result?: QueryResult;
  analysis?: string;
  chart_suggestion?: ChartSuggestion;
  success: boolean;
  error_message?: string;
  execution_time_ms: number;
  execution_steps: ExecutionStep[];
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content?: string;
  steps: ExecutionStep[];
  response?: AskResponse;
  status: 'pending' | 'success' | 'error';
  errorMessage?: string;
}

export type AskStreamEvent =
  | { type: 'step_start'; data: ExecutionStep }
  | { type: 'step'; data: ExecutionStep }
  | { type: 'result'; data: AskResponse };

export interface Session {
  session_id: string;
  title: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface HistoryMessage {
  role: 'user' | 'assistant';
  content: string;
  created_at: string | null;
}
