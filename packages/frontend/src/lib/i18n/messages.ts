/* UI message catalogue — care (照護端) and family (家屬端) surfaces only.
 *
 * The elder/voice surface is deliberately Chinese-only: MASTER.md §5.2. The
 * Taiwanese/Mandarin choice Module A cares about is the *spoken* interaction
 * language, which is domain data — never driven from this file.
 *
 * No i18n library on purpose (MASTER.md §0, ADR 0006 §5). `en` is typed as
 * Record<MessageKey, string>, so a missing or stray key fails `tsc`, not just
 * the runtime test in messages.test.ts.
 */

export const LOCALES = ['zh-Hant', 'en'] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = 'zh-Hant';

export function isLocale(value: unknown): value is Locale {
  return typeof value === 'string' && (LOCALES as readonly string[]).includes(value);
}

/** BCP 47 tag for Intl/`toLocaleString`. Not the same string as our own key. */
export function localeTag(locale: Locale): string {
  return locale === 'en' ? 'en-US' : 'zh-TW';
}

const zhHant = {
  // ---- language switch ----
  'lang.label': '語言',
  'lang.zh-Hant': '中文',
  'lang.en': 'English',

  // ---- shared ----
  'common.loading': '載入中…',
  'common.signIn': '前往登入 →',
  'common.continueWithGoogle': '使用 Google 繼續',
  'common.empty': '—',
  'common.version': '版本 {version}',
  /* Includes its own brackets: it always follows an item's text, and the
     bracket glyph itself differs between the two locales. */
  'common.sources': '（來源 {count} 筆）',

  // ---- credential states (care/family only; elder pages pass their own text) ----
  'auth.credentialUnavailable': '無法確認登入憑證狀態；系統已停止，不會略過認證',
  'auth.credentialMissing': '尚未設定登入資訊，請先完成登入設定',

  // ---- errors ----
  'error.noElderAccess': '目前身分沒有可查看的長者資料，請確認後端授權設定。',
  'error.reload': '讀取資料失敗，請重新整理。',
  'error.noFamilyReportAccess': '目前身分沒有查看這位長者家屬報表的權限。',
  'error.loadRecentFailed': '讀取近況失敗，請重新整理。',
  'error.loadReportsFailed': '讀取報表失敗，請重新整理。',
  'error.noElderDataPermission': '目前身分沒有查看或操作這位長者資料的權限。',
  'error.versionConflict': '資料版本已更新，請重新載入後再操作。',
  'error.loadEventsFailed': '讀取事件失敗',
  'error.loadMemoriesFailed': '讀取記憶失敗',
  'error.loadSummariesFailed': '讀取摘要失敗',
  'error.reviewEventFailed': '覆核事件失敗',

  // ---- caregiver dashboard ----
  'dashboard.title': '授權長者總覽',
  'dashboard.subtitle': '清單由 Core API 依目前登入身分與正式授權關係產生。',
  'dashboard.empty': '目前沒有已授權的長者資料。',
  'dashboard.colElder': '長者',
  'dashboard.colCareUnit': '照護單位',
  'dashboard.colAuthorization': '授權來源',
  'dashboard.authorized': '已授權',

  // ---- elder detail ----
  'elderDetail.title': '長者詳情',
  'elderDetail.tabEvents': '照護事件',
  'elderDetail.tabMemories': '記憶管理',
  'elderDetail.tabSummaries': '每日摘要',
  'elderDetail.summaryNotice': 'Core API 目前僅提供摘要讀取；摘要發布與家屬報表是不同的正式流程。',
  'elderDetail.summaryEmpty': '目前沒有正式摘要。',
  'elderDetail.summaryNoItems': '沒有可顯示的來源支持項目。',
  'elderDetail.dataGaps': '資料缺口：{fields}',

  // ---- event filters ----
  'eventFilter.dateFrom': '起始日期',
  'eventFilter.dateTo': '結束日期',
  'eventFilter.type': '類型',
  'eventFilter.status': '狀態',
  'eventFilter.allTypes': '全部',
  'eventFilter.officialEvents': '正式事件',

  // ---- event table ----
  'eventTable.empty': '沒有符合條件的事件紀錄。',
  'eventTable.colDate': '日期',
  'eventTable.colType': '類型',
  'eventTable.colContent': '內容',
  'eventTable.colConfidence': '信心區間',
  'eventTable.colStatus': '狀態',
  'eventTable.colEvidence': '證據／版本',
  'eventTable.colActions': '操作',
  'eventTable.evidenceVersion': '證據 {evidence} 筆｜版本 {version}',
  'eventTable.review': '覆核',
  'eventTable.submit': '送出覆核',
  'eventTable.cancel': '取消',

  // ---- review decisions (labels only; the enum sent to Core is unchanged) ----
  'decision.VERIFY': '驗證',
  'decision.CORRECT': '修正',
  'decision.REJECT': '拒絕',
  'decision.EXCLUDE': '排除',

  // ---- care event type (enum labels) ----
  'eventType.MEAL': '飲食',
  'eventType.ACTIVITY': '活動',
  'eventType.SLEEP': '睡眠',
  'eventType.MEDICATION_STATEMENT': '用藥陳述',
  'eventType.EMOTION_EXPRESSION': '情緒表達',
  'eventType.SOCIAL_CONTACT': '社交聯繫',
  'eventType.EXPECTED_CONTACT_MISSED': '未如期聯繫',
  'eventType.ACTIVITY_PARTICIPATION': '活動參與',
  'eventType.ACTIVITY_CANCELLED': '活動取消',
  'eventType.COMPANIONSHIP_NEED': '陪伴需求',

  // ---- care event status ----
  'eventStatus.CANDIDATE': '候選',
  'eventStatus.NEEDS_REVIEW': '待覆核',
  'eventStatus.VERIFIED': '已驗證',
  'eventStatus.CORRECTED': '已修正',
  'eventStatus.REJECTED': '已拒絕',
  'eventStatus.EXCLUDED': '已排除',

  // ---- confidence band ----
  'confidence.LOW': '低',
  'confidence.MEDIUM': '中',
  'confidence.HIGH': '高',

  // ---- memory ----
  'memoryType.PREFERENCE': '偏好',
  'memoryType.IMPORTANT_RELATIONSHIP': '重要關係',
  'memoryType.ROUTINE': '日常習慣',
  'memoryType.COMMUNICATION_PREFERENCE': '溝通偏好',
  'memoryType.PERSONAL_HISTORY': '個人經歷',
  'memory.candidatesTitle': '待確認候選記憶（{count}）',
  'memory.candidatesEmpty': '目前沒有待確認的候選記憶。',
  'memory.confirmedTitle': '有效記憶（{count}）',
  'memory.confirmedEmpty': '目前沒有有效記憶。',
  'memory.sourceEvents': '來源事件 {count} 筆｜版本 {version}',
  'memory.confirmedMeta': '確認者：{by}｜確認時間：{at}',
  'memory.confirm': '確認',
  'memory.reject': '拒絕',
  'memory.delete': '刪除',

  // ---- daily summary status ----
  'summaryStatus.DRAFT': '草稿',
  'summaryStatus.READY': '可供覆核',
  'summaryStatus.NEEDS_REVIEW': '待覆核',
  'summaryStatus.PUBLISHED': '已發布',
  'summaryStatus.STALE': '需重建',
  'summaryStatus.WITHDRAWN': '已撤回',

  // ---- family home ----
  'family.homeTitle': '家屬首頁',
  'family.meta': '長者：{elderId}｜最後更新：{updated}',
  'family.noData': '尚無資料',
  'family.todayTitle': '今日報表',
  'family.todayInsufficient': '今日資料不足。',
  'family.todayNone': '今日尚無已發布的家屬報表。',
  'family.weekTitle': '本週概覽',
  'family.weekNone': '本週尚無已發布的家屬報表。',
  'family.weekSummary':
    '本週有 {reports} 份正式報表，包含 {meals} 筆飲食與 {activities} 筆活動項目。',
  'family.importantTitle': '最新重要事件',
  'family.importantNone': '本週沒有可分享的重要事件。',
  'family.viewAll': '查看完整報表 →',

  // ---- family report centre ----
  'reports.back': '← 返回家屬首頁',
  'reports.title': '家屬報表中心',
  'reports.subtitle': '僅顯示 Core API 依關係授權與發布狀態篩選後的正式內容。',
  'reports.empty': '目前沒有可查看的已發布報表。',
  'reports.withdrawn': '此報表已撤回。',
  'reports.insufficient': '資料不足。',
  'reports.publishedAt': '版本 {version}｜發布時間：{at}',
  'reportType.DAILY': '每日報表',
  'reportType.WEEKLY': '每週報表',
  'reportType.MONTHLY': '每月報表',
  'reportType.IMPORTANT_EVENT': '重要事件報表',

  // ---- family onboarding / sign-in ----
  'join.title': '家屬服務',
  'join.intro':
    '請輸入服務單位提供的邀請碼。系統會先用 Google 確認您的身分，再確認您可查看的報表範圍。',
  'join.note': '邀請碼不會直接提供資料存取權；邀請核銷會在受保護的伺服器流程中完成。',
  'join.codeLabel': '家屬邀請碼',
  'join.alreadyBound': '已完成綁定？',
  'join.toFamilySignIn': '前往家屬登入',
  'join.backToChooser': '返回選擇服務',
  'familySignIn.title': '家屬登入',
  'familySignIn.body': '登入後只會顯示長者已同意分享、且仍在您授權範圍內的正式報表。',

  // ---- staff sign-in ----
  'staffSignIn.title': '照服員／居服員登入',
  'staffSignIn.body':
    '此帳號需要由所屬機構啟用。登入後，系統會依目前有效的機構歸屬與派案範圍顯示資料。',
  'staffSignIn.notActivated': '尚未啟用帳號？請聯絡所屬服務單位。',
} as const;

export type MessageKey = keyof typeof zhHant;

/* English wording notes:
   - Counts are rendered as "label: {count}" rather than "{count} items" so the
     catalogue needs no plural rules — the reason no i18n library is required yet.
   - Workflow-state labels stay literal ("Candidate", "Needs review"): they are
     domain states from `eldercare_ai`, not prose, and MASTER.md §4.2 requires the
     same state to read identically across all three surfaces. */
const en: Record<MessageKey, string> = {
  'lang.label': 'Language',
  'lang.zh-Hant': '中文',
  'lang.en': 'English',

  'common.loading': 'Loading…',
  'common.signIn': 'Go to sign-in →',
  'common.continueWithGoogle': 'Continue with Google',
  'common.empty': '—',
  'common.version': 'Version {version}',
  'common.sources': ' (sources: {count})',

  'auth.credentialUnavailable':
    'Credential status could not be verified. The system stopped rather than skipping authentication.',
  'auth.credentialMissing': 'Sign-in is not configured yet. Please complete sign-in setup first.',

  'error.noElderAccess':
    'This account has no elders it may view. Please check the backend authorization settings.',
  'error.reload': 'Could not load the data. Please refresh.',
  'error.noFamilyReportAccess':
    'This account is not permitted to view family reports for this elder.',
  'error.loadRecentFailed': 'Could not load recent activity. Please refresh.',
  'error.loadReportsFailed': 'Could not load reports. Please refresh.',
  'error.noElderDataPermission':
    'This account is not permitted to view or act on this elder’s data.',
  'error.versionConflict': 'This record has been updated. Please reload before acting on it.',
  'error.loadEventsFailed': 'Could not load care events',
  'error.loadMemoriesFailed': 'Could not load memories',
  'error.loadSummariesFailed': 'Could not load summaries',
  'error.reviewEventFailed': 'Could not submit the review',

  'dashboard.title': 'Authorized elders',
  'dashboard.subtitle':
    'The Core API builds this list from the signed-in identity and its recorded authorizations.',
  'dashboard.empty': 'No authorized elders yet.',
  'dashboard.colElder': 'Elder',
  'dashboard.colCareUnit': 'Care unit',
  'dashboard.colAuthorization': 'Authorization',
  'dashboard.authorized': 'Authorized',

  'elderDetail.title': 'Elder detail',
  'elderDetail.tabEvents': 'Care events',
  'elderDetail.tabMemories': 'Memories',
  'elderDetail.tabSummaries': 'Daily summaries',
  'elderDetail.summaryNotice':
    'The Core API currently exposes summaries read-only. Publishing a summary and publishing a family report are separate formal workflows.',
  'elderDetail.summaryEmpty': 'No formal summaries yet.',
  'elderDetail.summaryNoItems': 'No source-backed items to show.',
  'elderDetail.dataGaps': 'Data gaps: {fields}',

  'eventFilter.dateFrom': 'From',
  'eventFilter.dateTo': 'To',
  'eventFilter.type': 'Type',
  'eventFilter.status': 'Status',
  'eventFilter.allTypes': 'All',
  'eventFilter.officialEvents': 'Official events',

  'eventTable.empty': 'No care events match these filters.',
  'eventTable.colDate': 'Date',
  'eventTable.colType': 'Type',
  'eventTable.colContent': 'Content',
  'eventTable.colConfidence': 'Confidence',
  'eventTable.colStatus': 'Status',
  'eventTable.colEvidence': 'Evidence / version',
  'eventTable.colActions': 'Actions',
  'eventTable.evidenceVersion': 'evidence: {evidence} | version: {version}',
  'eventTable.review': 'Review',
  'eventTable.submit': 'Submit review',
  'eventTable.cancel': 'Cancel',

  'decision.VERIFY': 'Verify',
  'decision.CORRECT': 'Correct',
  'decision.REJECT': 'Reject',
  'decision.EXCLUDE': 'Exclude',

  'eventType.MEAL': 'Meal',
  'eventType.ACTIVITY': 'Activity',
  'eventType.SLEEP': 'Sleep',
  'eventType.MEDICATION_STATEMENT': 'Medication statement',
  'eventType.EMOTION_EXPRESSION': 'Emotion expressed',
  'eventType.SOCIAL_CONTACT': 'Social contact',
  'eventType.EXPECTED_CONTACT_MISSED': 'Expected contact missed',
  'eventType.ACTIVITY_PARTICIPATION': 'Activity participation',
  'eventType.ACTIVITY_CANCELLED': 'Activity cancelled',
  'eventType.COMPANIONSHIP_NEED': 'Companionship need',

  'eventStatus.CANDIDATE': 'Candidate',
  'eventStatus.NEEDS_REVIEW': 'Needs review',
  'eventStatus.VERIFIED': 'Verified',
  'eventStatus.CORRECTED': 'Corrected',
  'eventStatus.REJECTED': 'Rejected',
  'eventStatus.EXCLUDED': 'Excluded',

  'confidence.LOW': 'Low',
  'confidence.MEDIUM': 'Medium',
  'confidence.HIGH': 'High',

  'memoryType.PREFERENCE': 'Preference',
  'memoryType.IMPORTANT_RELATIONSHIP': 'Important relationship',
  'memoryType.ROUTINE': 'Routine',
  'memoryType.COMMUNICATION_PREFERENCE': 'Communication preference',
  'memoryType.PERSONAL_HISTORY': 'Personal history',
  'memory.candidatesTitle': 'Memory candidates awaiting confirmation ({count})',
  'memory.candidatesEmpty': 'No memory candidates awaiting confirmation.',
  'memory.confirmedTitle': 'Active memories ({count})',
  'memory.confirmedEmpty': 'No active memories.',
  'memory.sourceEvents': 'source events: {count} | version: {version}',
  'memory.confirmedMeta': 'Confirmed by: {by} | Confirmed at: {at}',
  'memory.confirm': 'Confirm',
  'memory.reject': 'Reject',
  'memory.delete': 'Delete',

  'summaryStatus.DRAFT': 'Draft',
  'summaryStatus.READY': 'Ready for review',
  'summaryStatus.NEEDS_REVIEW': 'Needs review',
  'summaryStatus.PUBLISHED': 'Published',
  'summaryStatus.STALE': 'Needs rebuild',
  'summaryStatus.WITHDRAWN': 'Withdrawn',

  'family.homeTitle': 'Family home',
  'family.meta': 'Elder: {elderId} | Last updated: {updated}',
  'family.noData': 'No data yet',
  'family.todayTitle': 'Today’s report',
  'family.todayInsufficient': 'Not enough data for today.',
  'family.todayNone': 'No published family report for today yet.',
  'family.weekTitle': 'This week',
  'family.weekNone': 'No published family reports this week yet.',
  'family.weekSummary':
    'This week has {reports} published report(s), covering {meals} meal and {activities} activity item(s).',
  'family.importantTitle': 'Recent important events',
  'family.importantNone': 'No shareable important events this week.',
  'family.viewAll': 'View all reports →',

  'reports.back': '← Back to family home',
  'reports.title': 'Family report centre',
  'reports.subtitle':
    'Shows only the formal content the Core API has filtered by relationship authorization and publication state.',
  'reports.empty': 'No published reports available to view.',
  'reports.withdrawn': 'This report has been withdrawn.',
  'reports.insufficient': 'Not enough data.',
  'reports.publishedAt': 'Version {version} | Published: {at}',
  'reportType.DAILY': 'Daily report',
  'reportType.WEEKLY': 'Weekly report',
  'reportType.MONTHLY': 'Monthly report',
  'reportType.IMPORTANT_EVENT': 'Important event report',

  'join.title': 'Family access',
  'join.intro':
    'Enter the invitation code your care provider gave you. We confirm your identity with Google first, then determine which reports you may see.',
  'join.note':
    'The invitation code does not grant data access by itself; redemption happens in a protected server-side flow.',
  'join.codeLabel': 'Family invitation code',
  'join.alreadyBound': 'Already linked?',
  'join.toFamilySignIn': 'Go to family sign-in',
  'join.backToChooser': 'Back to service selection',
  'familySignIn.title': 'Family sign-in',
  'familySignIn.body':
    'After signing in you will only see formal reports the elder has consented to share and that remain within your authorization.',

  'staffSignIn.title': 'Care worker sign-in',
  'staffSignIn.body':
    'This account must be activated by your organization. After signing in, data is shown according to your current organization membership and assignments.',
  'staffSignIn.notActivated': 'Account not activated yet? Please contact your service provider.',
};

export const MESSAGES: Record<Locale, Record<MessageKey, string>> = {
  'zh-Hant': zhHant,
  en,
};

export type MessageParams = Record<string, string | number>;

/**
 * Look up `key` and substitute `{name}` placeholders.
 *
 * An unknown placeholder is left verbatim rather than blanked, so a typo shows
 * up as `{foo}` on screen instead of silently producing a sentence that reads
 * fine but has lost a number.
 */
export function translate(locale: Locale, key: MessageKey, params?: MessageParams): string {
  const template = MESSAGES[locale][key];
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in params ? String(params[name]) : match,
  );
}
