import type { NextRequest } from 'next/server';
import { proxyCoreRequest } from '@/lib/server/core-proxy';

export const dynamic = 'force-dynamic';

interface RouteContext {
  params: { path: string[] };
}

function handle(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxyCoreRequest(request, context.params.path);
}

export const GET = handle;
export const HEAD = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
