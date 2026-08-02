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
  'common.signOut': '登出',
  'common.continueWithGoogle': '使用 Google 繼續',
  'common.empty': '—',
  'common.version': '版本 {version}',
  /* Includes its own brackets: it always follows an item's text, and the
     bracket glyph itself differs between the two locales. */
  'common.sources': '（來源 {count} 筆）',

  // ---- workflow states (MASTER.md §4.2) — the text half of colour+icon+text.
  //      Same wording on every surface: a state must read as the same state. ----
  'state.candidate': '未確認',
  'state.needsReview': '待覆核',
  'state.confirmed': '已確認',
  'state.published': '已發布',
  'state.withdrawn': '已撤回',
  'state.dataInsufficient': '資料不足',

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
  // §10.2 Needs Review — 數量與原因
  'needsReview.count': '有 {count} 筆照護事件等你覆核',
  'needsReview.countAtLeast': '至少有 {count} 筆照護事件等你覆核',
  'needsReview.byConfidence': '辨識信心：低 {low}｜中 {medium}｜高 {high}',
  'needsReview.reviewNow': '前往覆核',
  // §10.2 Permission Denied — 不顯示長者姓名或任何敏感內容
  'denied.title': '沒有查看權限',
  'denied.back': '返回長者總覽',

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
  'reports.period': '{start}～{end}',
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

  // ---- public surface (登入前行銷／法遵頁, MASTER.md §3 / §7.3) ----
  'a11y.skipToContent': '跳到主要內容',
  'public.header.brand': '智慧長照 AI 陪伴系統',
  'public.header.brandCompact': '小暖',
  'public.nav.primaryLabel': '主要導覽',
  'public.nav.footerLabel': '法遵與其他連結',
  'public.nav.about': '產品介紹',
  'public.nav.privacy': '隱私權政策',
  'public.nav.terms': '服務條款',
  'public.nav.dataRights': '資料權利',
  'public.nav.accessibility': '無障礙聲明',
  'public.nav.menu': '選單',
  'public.nav.close': '關閉選單',
  'public.cta.signIn': '登入',
  'public.footer.demoNotice':
    '本系統目前為開發／展示階段，畫面所見資料均為合成或去識別化範例，不包含真實長者資料。',

  // ---- landing page (signed-out `/`) ----
  'landing.hero.title': '小暖，陪伴長者的智慧語音夥伴',
  'landing.hero.subtitle':
    '結合語音互動、生活紀錄與照護者後台，用溫和不評判的方式陪伴長者，也讓家屬與照服員即時掌握近況。',
  'landing.hero.ctaPrimary': '開始使用',
  'landing.hero.ctaSecondary': '了解我們怎麼保護資料',

  'landing.modules.title': '這個系統做什麼',
  'landing.modules.subtitle':
    '三個核心模組對應長者、照護者與家屬的日常需求；以下如實標示目前的可用程度。',
  'landing.modules.status.available': '可以體驗',
  'landing.modules.status.partial': '部分可體驗',
  'landing.modules.status.planned': '規劃中',
  'landing.modules.a.title': 'Module A · 語音互動陪伴',
  'landing.modules.a.body':
    '文字陪伴對話已可使用；語音辨識（ASR）與語音合成（TTS）規劃中，目前互動以文字進行。',
  'landing.modules.b.title': 'Module B · 生活記錄與智慧摘要',
  'landing.modules.b.body':
    '對話中的照護事件可產生待覆核候選紀錄，經人工覆核後才成為正式紀錄；每日摘要為覆核後之正式內容，非模型任意生成。',
  'landing.modules.c.title': 'Module C · 照護者資訊介面',
  'landing.modules.c.body':
    '長者總覽、長者詳情、事件時間軸、覆核作業與家屬報表中心皆已可用，並依登入身分與正式授權顯示對應範圍的資料。',

  'landing.roles.title': '選擇您的身分開始',
  'landing.roles.subtitle': '三種身分各自對應不同的登入與畫面設計。',
  'landing.roles.elder.title': '我是長者',
  'landing.roles.elder.body': '用簡單的大按鈕開始陪伴對話，畫面文字與觸控目標皆放大設計。',
  'landing.roles.elder.cta': '長者開始使用',
  'landing.roles.family.title': '我是家屬',
  'landing.roles.family.body': '使用邀請碼或登入查看長者已同意分享的正式報表。',
  'landing.roles.family.cta': '家屬登入／加入',
  'landing.roles.staff.title': '我是照服員／居服員',
  'landing.roles.staff.body': '由所屬機構啟用帳號後，依派案與授權範圍查看長者資料。',
  'landing.roles.staff.cta': '照服員登入',

  'landing.privacy.title': '我們怎麼保護長者的資料',
  'landing.privacy.subtitle': '同意、覆核與撤回機制寫在產品規則裡，不是事後補充的聲明。',
  'landing.privacy.point1': '語音、記錄、記憶、家屬分享等用途分開取得同意，長者可分別開關。',
  'landing.privacy.point2': '對話中的候選紀錄與候選記憶，必須經明確確認或人工覆核，才會成為正式資料。',
  'landing.privacy.point3': '家屬只看得到已正式發布的報表；草稿與待覆核內容不會出現在家屬畫面。',
  'landing.privacy.point4':
    '長者說「不要記」或「停止」、或撤回同意時，系統立即優先處理，不受重試或排程影響。',
  'landing.privacy.cta': '閱讀完整隱私權政策 →',

  'landing.boundaries.title': '我們明確不做的事',
  'landing.boundaries.subtitle': '這些是產品規則，不是選配。',
  'landing.boundaries.item1': '不提供醫療診斷、治療建議，也不取代專業照護與醫療判斷。',
  'landing.boundaries.item2': '不把模型推論、缺少的資料或尚未覆核的內容當成已確認的事實。',
  'landing.boundaries.item3': '不使用恐懼、內疚、壓力或情緒依賴等方式提高使用率。',
  'landing.boundaries.item4': '不呈現健康燈號、風險評分或跨長者排名等易誤導的健康表徵。',
  'landing.boundaries.item5': '展示與測試一律使用模擬或去識別化資料，不使用真實長者資料。',

  'landing.closing.title': '準備好了嗎？',
  'landing.closing.body': '選擇上方的身分開始，或先閱讀我們的隱私權政策與資料權利說明。',
  'landing.closing.cta': '前往登入 →',

  // ---- public legal / compliance information ----
  'legal.common.kicker': '公開法遵資訊',
  'legal.common.updated': '最後更新：2026 年 8 月 2 日',
  'legal.common.noticeTitle': '目前狀態',

  // ---- privacy policy ----
  'legal.privacy.title': '隱私權政策',
  'legal.privacy.intro':
    '本頁說明智慧長照 AI 陪伴系統開發／展示版如何處理身分、對話、照護紀錄、同意與分享資料，以及目前尚未定案的事項。',
  'legal.privacy.notice':
    '本頁不是正式法律意見，也不是已核准的 production 隱私權聲明。正式營運前，仍需依實際地區、合作機構、資料治理與法務審查更新。',
  'legal.privacy.scope.title': '適用範圍與可能處理的資料',
  'legal.privacy.scope.body':
    '系統只應在明確用途、有效身分與授權範圍內處理完成任務所需的最小資料。開發與展示內容必須使用合成或完成去識別化的資料。',
  'legal.privacy.scope.item1':
    '登入與帳號資料，例如外部身分識別碼、顯示名稱、電子郵件、角色、機構歸屬與授權關係。',
  'legal.privacy.scope.item2':
    '在相對應同意與功能啟用時處理的對話、語音輸入、逐字稿與語言偏好；原始語音屬高度敏感資料。',
  'legal.privacy.scope.item3':
    '候選或已覆核的照護事件、已確認記憶、摘要、家屬報表及其來源與版本。',
  'legal.privacy.scope.item4':
    '同意、撤回、家屬分享範圍、刪除工作狀態，以及為安全與稽核所需的最小技術紀錄。',
  'legal.privacy.purpose.title': '用途分離與同意',
  'legal.privacy.purpose.body':
    '語音陪伴、逐字稿保存、事件擷取、長期記憶、陪伴訊號、主動陪伴與家屬分享是不同用途，不以單一總開關取代。',
  'legal.privacy.purpose.item1': '未取得對應用途的有效同意，不得開始或繼續該用途的處理。',
  'legal.privacy.purpose.item2':
    '撤回生效後先停止新的處理、排程、重試與分享，再依核准的保存與刪除流程處置既有資料。',
  'legal.privacy.purpose.item3':
    '介面語言偏好只影響畫面顯示，不會改寫長者的語音語言或任何正式同意。',
  'legal.privacy.access.title': '誰可以看到資料',
  'legal.privacy.access.body':
    '每次正式讀寫都需重新檢查登入身分、角色、tenant、長者、派案、關係、同意、用途、資料狀態與時間範圍；預設拒絕。',
  'legal.privacy.access.item1': '長者只能操作自己且目前允許的同意、記憶、分享與互動資料。',
  'legal.privacy.access.item2':
    '照服員與居服員只能在有效機構歸屬、派案與權限範圍內查看或覆核資料。',
  'legal.privacy.access.item3':
    '家屬只能看見長者已同意分享且正式發布的報表；草稿、待覆核內容與內部筆記不可見。',
  'legal.privacy.access.item4':
    '身分驗證、雲端代管、模型或搜尋等供應商只可依實際設定與受控用途處理必要資料；正式供應商清單仍待 production 核准。',
  'legal.privacy.ai.title': 'AI 內容不是自動成立的事實',
  'legal.privacy.ai.body':
    '模型輸出、候選事件與候選記憶可能不完整或有誤。未經長者明確確認或人工覆核，不得進入正式記憶、照護紀錄、家屬報表或後續對話事實；系統也不提供醫療診斷或治療決策。',
  'legal.privacy.retention.title': '保存、安全與刪除',
  'legal.privacy.retention.body1':
    '不同資料類別必須各自設定保存期限；原始音訊不預設永久保存。正式 Retention、備份例外、Legal Hold 與 Offboarding 政策目前尚待 Owner、法務與資料治理核准，因此本頁不承諾固定期限。',
  'legal.privacy.retention.body2':
    '刪除流程需追蹤正式資料、物件儲存、搜尋索引、Graph、Cache 與衍生結果，並可保留不含被刪內容的最小 Tombstone 防止資料因重試或還原復活。Token、Secret、完整逐字稿與不必要 Prompt 不得寫入一般日誌。',
  'legal.privacy.contact.title': '提出疑問或回報隱私問題',
  'legal.privacy.contact.body':
    '目前尚未建立正式對外資料保護窗口與回覆時限。請先透過提供服務的機構或專案維護管道提出，並避免在公開 Issue、訊息或截圖中附上真實長者資料、Token、完整對話或其他敏感內容。',

  // ---- terms of service ----
  'legal.terms.title': '服務條款',
  'legal.terms.intro':
    '本頁說明開發／展示版可接受的使用方式、帳號責任、醫療與安全邊界，以及服務目前的限制。',
  'legal.terms.notice':
    '這不是已核准的商用契約。正式定價、服務水準、責任限制、準據法、爭議處理、支援期限與 production 使用條款仍待 Owner 與法務核准。',
  'legal.terms.scope.title': '開發／展示版範圍',
  'legal.terms.scope.body':
    '本版本用於開發、測試與展示，尚未核准處理真實照護場域資料或作為 production 服務。Demo、測試、截圖與評估只能使用合成或完成去識別化的資料。',
  'legal.terms.accounts.title': '帳號、身分與授權',
  'legal.terms.accounts.body': '請只以自己的帳號與實際被授予的角色使用系統。知道網址、邀請碼或長者 ID 不等於取得資料權限。',
  'legal.terms.accounts.item1': '不得共用帳號、冒用身分、轉交登入狀態或規避機構啟用與派案限制。',
  'legal.terms.accounts.item2': '家屬邀請只能建立核准範圍內的關係與分享，不授予完整照護或管理權限。',
  'legal.terms.accounts.item3': '若發現帳號、裝置或邀請碼可能遭他人使用，應停止使用並通知服務機構或專案維護者。',
  'legal.terms.use.title': '可接受使用與禁止事項',
  'legal.terms.use.body': '使用者不得利用本系統傷害長者、取得未授權資料、干擾服務或將開發版當成正式照護依據。',
  'legal.terms.use.item1': '不得嘗試跨長者、跨 tenant、跨機構、跨角色或超出派案範圍讀寫資料。',
  'legal.terms.use.item2': '不得輸入真實長者個資、醫療資料、完整對話或可重用憑證作為 Demo／測試內容。',
  'legal.terms.use.item3': '不得上傳惡意內容、探測 Secret、繞過安全限制或故意耗盡系統資源。',
  'legal.terms.use.item4': '不得使用恐懼、內疚、壓力、欺騙或情緒依賴方式影響長者。',
  'legal.terms.safety.title': '不是醫療或緊急服務',
  'legal.terms.safety.body1':
    '系統不提供診斷、疾病機率、改藥、停藥、治療建議，也不取代醫師、護理師、照服員、家屬或其他專業人員的判斷。',
  'legal.terms.safety.body2':
    '若發生即刻危險、跌倒、失去意識、無法求助或其他緊急情況，請直接聯絡所在地的緊急服務或現場照護人員；本系統不能保證偵測事件或派遣救援。',
  'legal.terms.ai.title': 'AI 與資料限制',
  'legal.terms.ai.body':
    'AI 回覆可能延遲、不完整或有誤。候選內容在確認／覆核前不是正式事實；查無可靠資料時系統應明確說明資料不足，不得猜測。使用者仍需依角色完成必要的人工作業。',
  'legal.terms.availability.title': '服務可用性、變更與停止',
  'legal.terms.availability.body1':
    '開發版可能因部署、測試、依賴服務、權限或網路而中斷、變更或清除合成資料，目前不提供 production SLA。為保護安全、隱私或系統完整性，系統可拒絕或停止不合規的操作。',
  'legal.terms.availability.body2':
    '重大版本或政策變更應更新本頁日期並提供可理解的說明；正式商用前，必須以經核准的完整條款取代本頁。',

  // ---- data rights ----
  'legal.dataRights.title': '資料權利',
  'legal.dataRights.intro':
    '本頁用白話說明資料本人可能提出的查詢、更正、停止、刪除、匯出與撤回分享需求，以及開發版目前能做與尚未完成的部分。',
  'legal.dataRights.notice':
    '這是產品操作與治理說明，不是特定司法管轄區法定權利的完整清單。正式申請窗口、法定時限、Export 格式、Retention、Legal Hold 與例外處理仍待核准。',
  'legal.dataRights.rights.title': '可以提出哪些需求',
  'legal.dataRights.rights.body': '依適用法律、身分與合理例外，資料本人可提出下列需求；系統不得要求預先放棄依法不得放棄的權利。',
  'legal.dataRights.rights.item1': '查詢系統是否持有自己的個人資料，或請求閱覽。',
  'legal.dataRights.rights.item2': '請求取得自己資料的複製本或經核准的安全匯出。',
  'legal.dataRights.rights.item3': '補充或更正不完整、不正確的資料。',
  'legal.dataRights.rights.item4': '要求停止特定目的的蒐集、處理或利用，或撤回相對應同意。',
  'legal.dataRights.rights.item5': '在適用範圍內請求刪除資料。',
  'legal.dataRights.controls.title': '目前介面可操作的控制',
  'legal.dataRights.controls.body':
    '開發版只在已實作且通過授權的介面提供部分控制；看到一項權利說明，不代表自助流程已完整上線。',
  'legal.dataRights.controls.item1': '可查看並撤回目前已實作的 BASIC_VOICE 與 FAMILY_SHARING 同意。',
  'legal.dataRights.controls.item2': '可依角色與正式狀態管理家屬邀請、家屬分享或已確認記憶。',
  'legal.dataRights.controls.item3': '目前沒有公開的完整資料匯出或完整刪除申請自助入口。',
  'legal.dataRights.request.title': '如何提出需求',
  'legal.dataRights.request.body1':
    '正式窗口建立前，請透過提供服務的機構或專案維護管道說明申請人身分、角色、希望處理的資料範圍與需求類型；不要在公開管道貼出完整對話、身分文件、Token 或其他敏感資料。',
  'legal.dataRights.request.body2':
    '處理前必須驗證身分、tenant、長者、代理／家屬關係、派案與請求範圍。驗證失敗或可能暴露他人資料時必須拒絕，並以不洩漏敏感內容的方式說明。',
  'legal.dataRights.withdrawal.title': '撤回、停止分享與刪除並不相同',
  'legal.dataRights.withdrawal.body': '系統將不同目的與結果分開處理，避免使用者以為按下撤回就代表所有儲存位置已立即實體刪除。',
  'legal.dataRights.withdrawal.item1': '撤回同意生效後，先停止新的處理、重試、排程、通知與分享。',
  'legal.dataRights.withdrawal.item2': '刪除需由可追蹤的工作流處理正式儲存、物件、Graph、索引、Cache 與衍生資料。',
  'legal.dataRights.withdrawal.item3': '為防止已刪資料因重放或還原復活，可保留不含原內容的最小 Tombstone；備份與 Legal Hold 規則仍待核准。',
  'legal.dataRights.export.title': '安全匯出',
  'legal.dataRights.export.body':
    '匯出應是依角色、資料本人、用途與核准範圍產生的安全 Package，而不是資料庫 Dump；不得包含其他長者／tenant、未確認記憶、未覆核事件、草稿報表、完整 Prompt、Secret 或內部工作資料。正式格式、交付方式與完成時限尚未核准。',
  'legal.dataRights.representative.title': '家屬與代理人的範圍',
  'legal.dataRights.representative.body':
    '家屬身分或邀請碼不會自動取得代替長者行使所有資料權利的資格。系統只能依有效關係、同意、Share Scope 與適用代理授權處理，且不得透露範圍外資料。',

  // ---- accessibility statement ----
  'legal.accessibility.title': '無障礙聲明',
  'legal.accessibility.intro':
    '我們希望長者、家屬、照服員與使用輔助科技的人，都能理解與操作智慧長照 AI 陪伴系統。',
  'legal.accessibility.notice':
    '本系統以 WCAG 2.2 Level AA 作為設計參考目標，但尚未完成正式一致性評估、外部稽核或認證，因此不宣稱目前已完全符合。',
  'legal.accessibility.commitment.title': '我們的承諾',
  'legal.accessibility.commitment.body':
    '無障礙與長者可用性是產品規則的一部分，不是最後才補上的樣式。資訊應能被感知、介面可操作、內容可理解，並盡可能與不同瀏覽器及輔助科技相容。',
  'legal.accessibility.measures.title': '目前採取的措施',
  'legal.accessibility.measures.body': '目前前端設計與程式碼已採用下列措施，仍需持續以實際裝置與使用者驗證。',
  'legal.accessibility.measures.item1': '提供跳到主要內容連結、語意標題、landmark、可讀標籤與合理的焦點順序。',
  'legal.accessibility.measures.item2': '所有核心操作支援可見鍵盤焦點，不以移除 focus ring 換取視覺效果。',
  'legal.accessibility.measures.item3': '狀態不只靠顏色表達，搭配文字、圖示或不同形狀。',
  'legal.accessibility.measures.item4': '公共頁面使用至少 20px 內文與 56px 觸控目標；長者語音介面採更大的字級與觸控區。',
  'legal.accessibility.measures.item5': '不限制 pinch zoom，文字容器不以固定高度或裁切方式阻止放大與換行。',
  'legal.accessibility.measures.item6': '提供中英文介面；動畫尊重 reduced-motion 偏好，且資訊不只由動畫傳達。',
  'legal.accessibility.status.title': '評估狀態',
  'legal.accessibility.status.body':
    '目前已有自動化色彩對比測試與部分元件測試；完整鍵盤、螢幕閱讀器、系統字級 200%、平板橫直式與 390／768／1024／1280 寬度的人工驗收尚未全部完成。',
  'legal.accessibility.limitations.title': '已知限制',
  'legal.accessibility.limitations.body': '若遇到下列限制，請改用文字流程、重新整理或由現場人員協助，並回報發生情境。',
  'legal.accessibility.limitations.item1': '尚未完成各主要瀏覽器、作業系統、螢幕閱讀器與語音控制組合的相容性矩陣。',
  'legal.accessibility.limitations.item2': '部分頁面的 200% 系統字級與所有斷點人工檢查仍在進行。',
  'legal.accessibility.limitations.item3': '完整 ASR、TTS 與每個長者語音狀態的音訊提示尚未成為 production 可用功能。',
  'legal.accessibility.technology.title': '所使用的技術',
  'legal.accessibility.technology.body':
    '介面依賴現代瀏覽器的 HTML、CSS、JavaScript、SVG 與必要的 WAI-ARIA。一般法遵內容可直接閱讀；語音互動另需可用網路、麥克風權限與受支援的瀏覽器能力。',
  'legal.accessibility.feedback.title': '回報無障礙問題',
  'legal.accessibility.feedback.body1':
    '目前尚未建立正式無障礙聯絡窗口與回覆 SLA。請先透過提供服務的機構或專案維護管道回報頁面、瀏覽器／裝置、使用的輔助科技、遇到的障礙與希望完成的操作。',
  'legal.accessibility.feedback.body2':
    '請勿在回報中附上真實長者姓名、完整對話、Token、照護紀錄或其他敏感資料；可使用合成範例說明問題。',
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
  'common.signOut': 'Sign out',
  'common.continueWithGoogle': 'Continue with Google',
  'common.empty': '—',
  'common.version': 'Version {version}',
  'common.sources': ' (sources: {count})',

  'state.candidate': 'Candidate',
  'state.needsReview': 'Needs review',
  'state.confirmed': 'Confirmed',
  'state.published': 'Published',
  'state.withdrawn': 'Withdrawn',
  'state.dataInsufficient': 'Not enough data',

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
  'needsReview.count': '{count} care events are waiting for your review',
  'needsReview.countAtLeast': 'At least {count} care events are waiting for your review',
  'needsReview.byConfidence':
    'Recognition confidence — low: {low} | medium: {medium} | high: {high}',
  'needsReview.reviewNow': 'Review now',
  'denied.title': 'No access',
  'denied.back': 'Back to elder list',

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
  'reports.period': '{start} – {end}',
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

  // ---- public surface ----
  'a11y.skipToContent': 'Skip to main content',
  'public.header.brand': 'Smart Eldercare AI Companion',
  'public.header.brandCompact': 'Xiao Nuan',
  'public.nav.primaryLabel': 'Primary navigation',
  'public.nav.footerLabel': 'Legal and other links',
  'public.nav.about': 'About',
  'public.nav.privacy': 'Privacy policy',
  'public.nav.terms': 'Terms of service',
  'public.nav.dataRights': 'Data rights',
  'public.nav.accessibility': 'Accessibility statement',
  'public.nav.menu': 'Menu',
  'public.nav.close': 'Close menu',
  'public.cta.signIn': 'Sign in',
  'public.footer.demoNotice':
    'This system is currently in development/demo stage. All data shown is synthetic or de-identified — no real elder data is included.',

  // ---- landing page (signed-out `/`) ----
  'landing.hero.title': 'Xiao Nuan — a gentle voice companion for elder care',
  'landing.hero.subtitle':
    'Voice interaction, daily-life records, and a caregiver dashboard work together to support elders warmly and without judgment, while keeping family and care staff informed.',
  'landing.hero.ctaPrimary': 'Get started',
  'landing.hero.ctaSecondary': 'See how we protect your data',

  'landing.modules.title': 'What this system does',
  'landing.modules.subtitle':
    'Three core modules map to the daily needs of elders, caregivers, and family — the status below reflects what actually works today.',
  'landing.modules.status.available': 'Available now',
  'landing.modules.status.partial': 'Partially available',
  'landing.modules.status.planned': 'Planned',
  'landing.modules.a.title': 'Module A · Voice companionship',
  'landing.modules.a.body':
    'Text-based companion conversation works today. Speech recognition (ASR) and speech synthesis (TTS) are planned; interaction is currently text-only.',
  'landing.modules.b.title': 'Module B · Life records & smart summaries',
  'landing.modules.b.body':
    'Conversations can produce candidate care-event records awaiting human review; only reviewed records become official. Daily summaries are formally reviewed content, not free-form model output.',
  'landing.modules.c.title': 'Module C · Caregiver information interface',
  'landing.modules.c.body':
    'Elder overview, elder detail, event timeline, review workflow, and the family report centre are all available today, scoped to the signed-in identity’s formal authorization.',

  'landing.roles.title': 'Choose your role to begin',
  'landing.roles.subtitle': 'Each role has its own sign-in flow and screen design.',
  'landing.roles.elder.title': 'I am an elder',
  'landing.roles.elder.body':
    'Start a companion conversation with large buttons — text and touch targets are enlarged throughout.',
  'landing.roles.elder.cta': 'Start as an elder',
  'landing.roles.family.title': 'I am a family member',
  'landing.roles.family.body':
    'Use an invitation code or sign in to view the formal reports the elder has agreed to share.',
  'landing.roles.family.cta': 'Family sign-in / join',
  'landing.roles.staff.title': 'I am a care worker',
  'landing.roles.staff.body':
    'Once your organization activates your account, you will see elder data scoped to your assignments and authorization.',
  'landing.roles.staff.cta': 'Care worker sign-in',

  'landing.privacy.title': 'How we protect elders’ data',
  'landing.privacy.subtitle': 'Consent, review, and revocation are built into the product rules — not an afterthought.',
  'landing.privacy.point1':
    'Consent is split by purpose — voice, recording, memory, family sharing and more — and the elder can toggle each one independently.',
  'landing.privacy.point2':
    'Candidate records and candidate memories from a conversation only become official after explicit confirmation or human review.',
  'landing.privacy.point3':
    'Family members only see formally published reports; drafts and unreviewed content never reach the family screen.',
  'landing.privacy.point4':
    'When an elder says "don’t remember this" or "stop", or revokes consent, the system honors it immediately — ahead of any retry or scheduled job.',
  'landing.privacy.cta': 'Read the full privacy policy →',

  'landing.boundaries.title': 'What we deliberately do not do',
  'landing.boundaries.subtitle': 'These are product rules, not optional extras.',
  'landing.boundaries.item1':
    'No medical diagnosis or treatment advice, and no replacing professional care or medical judgment.',
  'landing.boundaries.item2':
    'Model inferences, missing data, or unreviewed content are never presented as confirmed fact.',
  'landing.boundaries.item3': 'No fear, guilt, pressure, or emotional-dependency tactics to drive usage.',
  'landing.boundaries.item4':
    'No health-status indicators, risk scores, or cross-elder rankings that could mislead.',
  'landing.boundaries.item5':
    'All demos and tests use synthetic or de-identified data — never a real elder’s data.',

  'landing.closing.title': 'Ready to begin?',
  'landing.closing.body': 'Choose a role above, or read our privacy policy and data-rights page first.',
  'landing.closing.cta': 'Go to sign-in →',

  // ---- public legal / compliance information ----
  'legal.common.kicker': 'Public legal and compliance information',
  'legal.common.updated': 'Last updated: August 2, 2026',
  'legal.common.noticeTitle': 'Current status',

  // ---- privacy policy ----
  'legal.privacy.title': 'Privacy Policy',
  'legal.privacy.intro':
    'This page explains how the development/demo version of the Smart Eldercare AI Companion handles identity, conversation, care-record, consent, and sharing data, including matters that are not yet approved.',
  'legal.privacy.notice':
    'This page is not legal advice or an approved production privacy notice. It must be updated for the actual jurisdiction, partner organization, data-governance decisions, and legal review before production use.',
  'legal.privacy.scope.title': 'Scope and data we may process',
  'legal.privacy.scope.body':
    'The system should process only the minimum data required for a clear purpose and within a valid identity and authorization scope. Development and demo content must use synthetic or properly de-identified data.',
  'legal.privacy.scope.item1':
    'Sign-in and account data, such as an external subject identifier, display name, email address, role, organization membership, and authorization relationship.',
  'legal.privacy.scope.item2':
    'Conversation, voice input, transcript, and language-preference data when the corresponding consent and feature are active; raw voice is highly sensitive data.',
  'legal.privacy.scope.item3':
    'Candidate or reviewed care events, confirmed memories, summaries, family reports, and their sources and versions.',
  'legal.privacy.scope.item4':
    'Consent, revocation, family-sharing scope, deletion-job status, and the minimum technical records required for security and audit.',
  'legal.privacy.purpose.title': 'Separate purposes and consent',
  'legal.privacy.purpose.body':
    'Voice companionship, transcript storage, care-event extraction, long-term memory, companion-signal analysis, proactive companionship, and family sharing are separate purposes; one blanket switch must not replace them.',
  'legal.privacy.purpose.item1': 'Processing for a purpose must not begin or continue without valid consent for that purpose.',
  'legal.privacy.purpose.item2':
    'Once revocation takes effect, new processing, schedules, retries, and sharing stop first; existing data then follows an approved retention and deletion workflow.',
  'legal.privacy.purpose.item3':
    'The interface-language preference changes display only; it never changes the elder’s spoken-language preference or any formal consent.',
  'legal.privacy.access.title': 'Who may access data',
  'legal.privacy.access.body':
    'Every formal read and write must re-check identity, role, tenant, elder, assignment, relationship, consent, purpose, resource state, and time scope. The default is deny.',
  'legal.privacy.access.item1': 'Elders may act only on their own currently permitted consent, memory, sharing, and interaction data.',
  'legal.privacy.access.item2':
    'Care workers may view or review data only within an active organization membership, assignment, and permission scope.',
  'legal.privacy.access.item3':
    'Family members see only formally published reports the elder agreed to share; drafts, unreviewed material, and internal notes are hidden.',
  'legal.privacy.access.item4':
    'Identity, cloud-hosting, model, or search providers may process necessary data only for configured and controlled purposes; the production subprocessor list is not yet approved.',
  'legal.privacy.ai.title': 'AI content is not automatically a confirmed fact',
  'legal.privacy.ai.body':
    'Model output, candidate events, and candidate memories may be incomplete or wrong. Until the elder explicitly confirms them or a human reviews them, they must not enter formal memory, care records, family reports, or later conversation as fact. The system also does not provide medical diagnosis or treatment decisions.',
  'legal.privacy.retention.title': 'Retention, security, and deletion',
  'legal.privacy.retention.body1':
    'Each data category needs its own retention period, and raw audio is not permanent by default. Formal retention, backup exceptions, legal hold, and offboarding policies still require owner, legal, and data-governance approval, so this page promises no fixed period.',
  'legal.privacy.retention.body2':
    'Deletion workflows must track authoritative stores, object storage, search indexes, graphs, caches, and derived results. A minimal tombstone without deleted content may remain to prevent replay or restore from reviving data. Tokens, secrets, full transcripts, and unnecessary prompt content must not enter ordinary logs.',
  'legal.privacy.contact.title': 'Questions and privacy reports',
  'legal.privacy.contact.body':
    'A formal public privacy contact and response time have not yet been established. For now, contact the organization providing the service or the project-maintenance channel, and never attach real elder data, tokens, full conversations, or other sensitive material to public issues, messages, or screenshots.',

  // ---- terms of service ----
  'legal.terms.title': 'Terms of Service',
  'legal.terms.intro':
    'This page describes acceptable use of the development/demo version, account responsibilities, medical and safety boundaries, and current service limitations.',
  'legal.terms.notice':
    'These are not approved commercial terms. Pricing, service levels, limitations of liability, governing law, dispute handling, support periods, and production-use terms still require owner and legal approval.',
  'legal.terms.scope.title': 'Development/demo scope',
  'legal.terms.scope.body':
    'This version is for development, testing, and demonstration and is not approved for real care-setting data or production service. Demos, tests, screenshots, and evaluations may use only synthetic or properly de-identified data.',
  'legal.terms.accounts.title': 'Accounts, identity, and authorization',
  'legal.terms.accounts.body':
    'Use only your own account and the role actually granted to you. Knowing a URL, invitation code, or elder ID does not create permission to access data.',
  'legal.terms.accounts.item1': 'Do not share accounts, impersonate another person, transfer a session, or bypass organization activation and assignment limits.',
  'legal.terms.accounts.item2': 'A family invitation establishes only the approved relationship and sharing scope; it does not grant full care or administration rights.',
  'legal.terms.accounts.item3': 'If an account, device, or invitation code may be in someone else’s hands, stop using it and notify the service organization or project maintainer.',
  'legal.terms.use.title': 'Acceptable use and prohibited conduct',
  'legal.terms.use.body':
    'Do not use the system to harm elders, obtain unauthorized data, disrupt service, or treat a development build as an authoritative care system.',
  'legal.terms.use.item1': 'Do not attempt cross-elder, cross-tenant, cross-organization, cross-role, or out-of-assignment data access.',
  'legal.terms.use.item2': 'Do not enter real elder personal data, medical data, full conversations, or reusable credentials into demos or tests.',
  'legal.terms.use.item3': 'Do not upload malicious content, probe secrets, bypass safeguards, or deliberately exhaust system resources.',
  'legal.terms.use.item4': 'Do not use fear, guilt, pressure, deception, or emotional-dependency tactics to influence an elder.',
  'legal.terms.safety.title': 'Not a medical or emergency service',
  'legal.terms.safety.body1':
    'The system does not provide diagnoses, disease probabilities, medication changes, treatment advice, or a substitute for clinicians, care workers, family, or other professionals.',
  'legal.terms.safety.body2':
    'For immediate danger, a fall, loss of consciousness, inability to call for help, or another emergency, contact local emergency services or on-site care staff directly. This system cannot guarantee event detection or dispatch assistance.',
  'legal.terms.ai.title': 'AI and data limitations',
  'legal.terms.ai.body':
    'AI responses may be delayed, incomplete, or wrong. Candidate content is not formal fact until confirmation or review. When reliable information is unavailable, the system should say so rather than guess. Users must still complete the human work required by their role.',
  'legal.terms.availability.title': 'Availability, change, and suspension',
  'legal.terms.availability.body1':
    'The development version may be interrupted, changed, or have synthetic data cleared because of deployment, testing, dependencies, permissions, or network conditions. It has no production SLA. Operations may be denied or stopped to protect safety, privacy, or system integrity.',
  'legal.terms.availability.body2':
    'Material version or policy changes should update this page’s date and provide an understandable explanation. Approved full terms must replace this page before commercial production use.',

  // ---- data rights ----
  'legal.dataRights.title': 'Data Rights',
  'legal.dataRights.intro':
    'This page explains in plain language how a data subject may ask to access, correct, stop, delete, export, or withdraw sharing, including what the development version can and cannot do today.',
  'legal.dataRights.notice':
    'This is product and governance guidance, not a complete list of statutory rights for any jurisdiction. The formal request channel, legal deadlines, export format, retention, legal hold, and exception handling remain unapproved.',
  'legal.dataRights.rights.title': 'Requests you may make',
  'legal.dataRights.rights.body':
    'Subject to applicable law, verified identity, and reasonable exceptions, a data subject may make the following requests. The system must not require advance waiver of rights that the law makes non-waivable.',
  'legal.dataRights.rights.item1': 'Ask whether the system holds your personal data and request access to it.',
  'legal.dataRights.rights.item2': 'Request a copy of your data or an approved secure export.',
  'legal.dataRights.rights.item3': 'Supplement or correct incomplete or inaccurate data.',
  'legal.dataRights.rights.item4': 'Ask to stop collection, processing, or use for a purpose, or withdraw the corresponding consent.',
  'legal.dataRights.rights.item5': 'Request deletion within the applicable scope.',
  'legal.dataRights.controls.title': 'Controls available in the current interface',
  'legal.dataRights.controls.body':
    'The development version exposes only some controls through implemented, authorized screens. A right described on this page does not mean that its self-service workflow is complete.',
  'legal.dataRights.controls.item1': 'Review and revoke the currently implemented BASIC_VOICE and FAMILY_SHARING consents.',
  'legal.dataRights.controls.item2': 'Manage family invitations, family sharing, or confirmed memories where the relevant role-specific interface exists.',
  'legal.dataRights.controls.item3': 'There is currently no public self-service flow for a complete data export or complete deletion request.',
  'legal.dataRights.request.title': 'How to make a request',
  'legal.dataRights.request.body1':
    'Until a formal channel exists, contact the organization providing the service or the project-maintenance channel with your identity, role, requested data scope, and request type. Do not post full conversations, identity documents, tokens, or other sensitive data publicly.',
  'legal.dataRights.request.body2':
    'Before acting, the system must verify identity, tenant, elder, representative or family relationship, assignment, and request scope. It must refuse a request that fails verification or may expose another person’s data, using an explanation that does not leak sensitive details.',
  'legal.dataRights.withdrawal.title': 'Revocation, stopping sharing, and deletion are different',
  'legal.dataRights.withdrawal.body':
    'The system separates purposes and outcomes so that pressing revoke is not mistaken for immediate physical deletion from every storage location.',
  'legal.dataRights.withdrawal.item1': 'Once consent revocation takes effect, new processing, retries, schedules, notifications, and sharing stop first.',
  'legal.dataRights.withdrawal.item2': 'Deletion requires a traceable workflow across authoritative stores, objects, graphs, indexes, caches, and derived data.',
  'legal.dataRights.withdrawal.item3': 'A minimal tombstone without original content may remain to prevent replay or restore from reviving data; backup and legal-hold rules are not yet approved.',
  'legal.dataRights.export.title': 'Secure export',
  'legal.dataRights.export.body':
    'An export should be a secure package limited by role, data subject, purpose, and approved scope—not a database dump. It must exclude other elders or tenants, unconfirmed memories, unreviewed events, draft reports, full prompts, secrets, and internal working data. The final format, delivery method, and completion timeline are not yet approved.',
  'legal.dataRights.representative.title': 'Family and representative scope',
  'legal.dataRights.representative.body':
    'Family status or an invitation code does not automatically authorize someone to exercise every data right for an elder. Requests may proceed only within a valid relationship, consent, share scope, and applicable representative authority, without revealing out-of-scope data.',

  // ---- accessibility statement ----
  'legal.accessibility.title': 'Accessibility Statement',
  'legal.accessibility.intro':
    'We want elders, family members, care workers, and people who use assistive technology to understand and operate the Smart Eldercare AI Companion.',
  'legal.accessibility.notice':
    'WCAG 2.2 Level AA is a design reference goal for this system, but formal conformance evaluation, external audit, and certification have not been completed. We therefore do not claim full conformance today.',
  'legal.accessibility.commitment.title': 'Our commitment',
  'legal.accessibility.commitment.body':
    'Accessibility and elder usability are product rules, not final styling. Information should be perceivable, interfaces operable, content understandable, and implementation as robust as practical across browsers and assistive technologies.',
  'legal.accessibility.measures.title': 'Measures currently in place',
  'legal.accessibility.measures.body':
    'The current frontend design and code use the following measures, which still require ongoing validation on real devices and with users.',
  'legal.accessibility.measures.item1': 'A skip-to-content link, semantic headings, landmarks, readable labels, and a logical focus order.',
  'legal.accessibility.measures.item2': 'Visible keyboard focus for core controls; focus rings are not removed for visual styling.',
  'legal.accessibility.measures.item3': 'State is not conveyed by color alone; text, icons, or distinct shapes accompany it.',
  'legal.accessibility.measures.item4': 'Public pages use at least 20px body text and 56px touch targets; the elder voice interface uses larger type and controls.',
  'legal.accessibility.measures.item5': 'Pinch zoom is not restricted, and text containers avoid fixed heights and clipping that would block enlargement or wrapping.',
  'legal.accessibility.measures.item6': 'Chinese and English interfaces are available; motion respects reduced-motion preferences, and information is not carried by animation alone.',
  'legal.accessibility.status.title': 'Assessment status',
  'legal.accessibility.status.body':
    'Automated color-contrast tests and some component tests exist. Full keyboard, screen-reader, 200% system-text, tablet-orientation, and 390/768/1024/1280-width manual acceptance testing is not yet complete.',
  'legal.accessibility.limitations.title': 'Known limitations',
  'legal.accessibility.limitations.body':
    'If you encounter one of these limitations, use the text-based path, refresh, or ask on-site staff for help, and report the context in which it occurred.',
  'legal.accessibility.limitations.item1': 'A compatibility matrix across major browsers, operating systems, screen readers, and voice-control tools is not complete.',
  'legal.accessibility.limitations.item2': 'Manual checks for 200% system text and every supported breakpoint are still in progress on some pages.',
  'legal.accessibility.limitations.item3': 'Complete ASR, TTS, and audio cues for every elder voice state are not yet production-ready features.',
  'legal.accessibility.technology.title': 'Technologies used',
  'legal.accessibility.technology.body':
    'The interface relies on modern-browser support for HTML, CSS, JavaScript, SVG, and necessary WAI-ARIA. General legal content can be read directly; voice interaction also requires a working network, microphone permission, and supported browser capabilities.',
  'legal.accessibility.feedback.title': 'Reporting an accessibility barrier',
  'legal.accessibility.feedback.body1':
    'A formal accessibility contact and response SLA have not yet been established. For now, report the page, browser or device, assistive technology, barrier encountered, and task you were trying to complete through the service organization or project-maintenance channel.',
  'legal.accessibility.feedback.body2':
    'Do not include real elder names, full conversations, tokens, care records, or other sensitive data in a report. Use a synthetic example where possible.',
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
