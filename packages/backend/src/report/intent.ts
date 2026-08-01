const YEAR_KEYWORDS = ['這一年', '今年', '去年', '一年來', '過去一年'];

// Deliberately specific request phrasing, not bare words like "紀錄" that
// also show up in ordinary event statements ("我今天的用藥紀錄") — a false
// positive here would silently swap a normal reply for a canned report.
const REPORT_TRIGGER_KEYWORDS = ['過得如何', '過得怎麼樣', '生活紀錄', '生活狀況', '回顧一下', '整理報表', '摘要報表'];

/**
 * A07.3 — "WHEN Elder 以語音詢問生活紀錄，THE System SHALL 以語音回覆對應時間
 * 範圍之摘要". Keyword heuristic, not full NLU — good enough for the demo
 * script's explicit phrasing, not a general intent classifier. Returns the
 * requested range, or null if the utterance isn't a report request at all.
 */
export function detectReportIntent(utterance: string): 'week' | 'year' | null {
  const hasTrigger = REPORT_TRIGGER_KEYWORDS.some((k) => utterance.includes(k));
  if (!hasTrigger) return null;

  if (YEAR_KEYWORDS.some((k) => utterance.includes(k))) return 'year';
  // Trigger present but no explicit range mentioned — default to week,
  // matching computeReport's own default in api/reports.ts.
  return 'week';
}
