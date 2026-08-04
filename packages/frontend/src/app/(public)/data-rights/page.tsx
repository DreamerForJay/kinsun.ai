import type { Metadata } from 'next';
import { LegalPage } from '@/components/public/LegalPage';

export const metadata: Metadata = {
  title: '資料權利｜智慧長照 AI 陪伴系統',
  description: '如何查詢、更正、撤回同意、停止分享、申請刪除或匯出資料。',
};

export default function DataRightsPage() {
  return <LegalPage page="dataRights" />;
}
