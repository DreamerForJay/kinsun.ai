import type { Metadata } from 'next';
import { LegalPage } from '@/components/public/LegalPage';

export const metadata: Metadata = {
  title: '無障礙聲明｜智慧長照 AI 陪伴系統',
  description: '本系統的無障礙設計措施、目前評估狀態、已知限制與回報方式。',
};

export default function AccessibilityPage() {
  return <LegalPage page="accessibility" />;
}
