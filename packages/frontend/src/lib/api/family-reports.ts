import { apiFetch, type ApiConfig } from './client';

export type FamilyReportType = 'DAILY' | 'WEEKLY' | 'MONTHLY' | 'IMPORTANT_EVENT';
export type FamilyReportStatus = 'DRAFT' | 'NEEDS_REVIEW' | 'PUBLISHED' | 'WITHDRAWN' | 'STALE';

interface CoreFamilyReportItem {
  category: string;
  text: string;
  source_ids: string[];
}

interface CoreFamilyReport {
  report_id: string;
  elder_id: string;
  recipient_scope_ids: string[];
  report_type: FamilyReportType;
  period_start: string;
  period_end: string;
  status: FamilyReportStatus;
  items: CoreFamilyReportItem[];
  data_gap_notice: string | null;
  sensitive_review_required: boolean;
  version: number;
  published_at: string | null;
  withdrawn_at: string | null;
  updated_at: string;
}

interface CoreFamilyReportList {
  items: CoreFamilyReport[];
}

export interface FamilyReportItemView {
  category: string;
  text: string;
  sourceIds: string[];
}

export interface FamilyReportView {
  reportId: string;
  elderId: string;
  reportType: FamilyReportType;
  periodStart: string;
  periodEnd: string;
  status: FamilyReportStatus;
  items: FamilyReportItemView[];
  dataGapNotice: string | null;
  version: number;
  publishedAt: string | null;
  withdrawnAt: string | null;
  updatedAt: string;
}

function toFamilyReportView(report: CoreFamilyReport): FamilyReportView {
  return {
    reportId: report.report_id,
    elderId: report.elder_id,
    reportType: report.report_type,
    periodStart: report.period_start,
    periodEnd: report.period_end,
    status: report.status,
    items: report.items.map((item) => ({
      category: item.category,
      text: item.text,
      sourceIds: item.source_ids,
    })),
    dataGapNotice: report.data_gap_notice,
    version: report.version,
    publishedAt: report.published_at,
    withdrawnAt: report.withdrawn_at,
    updatedAt: report.updated_at,
  };
}

/** Family reads only Core-filtered reports within the authenticated relationship scope. */
export async function listFamilyReports(
  config: ApiConfig,
  elderId: string,
  reportType?: FamilyReportType,
): Promise<FamilyReportView[]> {
  const query = reportType ? `?type=${encodeURIComponent(reportType)}` : '';
  const result = await apiFetch<CoreFamilyReportList>(
    config,
    `/api/v1/family/elders/${elderId}/reports${query}`,
  );
  return result.items.map(toFamilyReportView);
}
