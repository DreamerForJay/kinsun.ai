'use client';

import Link from 'next/link';
import type { DashboardElder } from '@/lib/api/dashboard';

export interface ElderOverviewListProps {
  elders: DashboardElder[];
}

export function ElderOverviewList({ elders }: ElderOverviewListProps) {
  if (elders.length === 0) {
    return <p style={{ color: '#718096' }}>目前沒有已授權的長者資料。</p>;
  }

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr style={{ textAlign: 'left', borderBottom: '2px solid #e2e8f0' }}>
          <th style={{ padding: 8 }}>長者</th>
          <th style={{ padding: 8 }}>照護單位</th>
          <th style={{ padding: 8 }}>授權來源</th>
        </tr>
      </thead>
      <tbody>
        {elders.map((elder) => (
          <tr key={elder.elderId} style={{ borderBottom: '1px solid #edf2f7' }}>
            <td style={{ padding: 8 }}>
              <Link href={`/dashboard/${elder.elderId}`} style={{ color: '#2b6cb0' }}>
                {elder.elderName}
              </Link>
            </td>
            <td style={{ padding: 8 }}>{elder.careUnitName ?? '—'}</td>
            <td style={{ padding: 8 }}>{elder.authorizationSummary ?? '已授權'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
