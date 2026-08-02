import type { Metadata } from 'next';
import { LegalPage } from '@/components/public/LegalPage';

export const metadata: Metadata = {
  title: '隱私權政策｜智慧長照 AI 陪伴系統',
  description: '智慧長照 AI 陪伴系統開發／展示版的資料處理、同意、分享與刪除原則。',
};

export default function PrivacyPage() {
  return <LegalPage page="privacy" />;
}
