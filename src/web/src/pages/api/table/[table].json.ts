/**
 * One page of one whitelisted catalog table (plan D5). The TanStack island
 * calls this on every page/sort/filter change; the client never receives
 * more than one page (max 100 rows).
 */
import type { APIRoute } from 'astro';
import { TABLES, parsePageQuery, queryPage } from '../../../lib/tables';

export const GET: APIRoute = ({ params, url }) => {
  const spec = TABLES[params.table ?? ''];
  if (!spec) {
    return new Response(JSON.stringify({ error: 'unknown_table' }), {
      status: 404,
      headers: { 'Content-Type': 'application/json' },
    });
  }
  const result = queryPage(spec, parsePageQuery(spec, url.searchParams));
  if (result === null) {
    return new Response(JSON.stringify({ error: 'catalog_missing' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  }
  return new Response(JSON.stringify(result), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
};
