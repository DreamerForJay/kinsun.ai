import type { NextRequest } from 'next/server';
import { proxyCoreRequest } from '@/lib/server/core-proxy';

export const dynamic = 'force-dynamic';

interface RouteContext {
  params: Promise<{ path: string[] }>;
}

async function handle(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path } = await context.params;
  return proxyCoreRequest(request, path);
}

export const GET = handle;
export const HEAD = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
