import type { Metadata } from 'next';
import { LegalPage } from '@/components/public/LegalPage';

export const metadata: Metadata = {
  title: '服務條款｜智慧長照 AI 陪伴系統',
  description: '智慧長照 AI 陪伴系統開發／展示版的使用範圍、安全邊界與限制。',
};

export default function TermsPage() {
  return <LegalPage page="terms" />;
}
