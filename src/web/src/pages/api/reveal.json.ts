/**
 * Reveal a source item in the OS file explorer, or open it with its default
 * app (plan D5 follow-up). The viewer only binds to 127.0.0.1 (see `even
 * serve`), so this is a local, single-user action — the same trust boundary
 * as running `even` itself from a terminal on this machine.
 *
 * The absolute path never round-trips through the client: the request only
 * carries a whitelisted table name + row id, and the path is looked up here
 * from the read-only catalog (see `REVEALABLE` in lib/tables.ts).
 */
import type { APIRoute } from 'astro';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import { catalog, catalogTableNames } from '../../lib/catalog';
import { REVEALABLE } from '../../lib/tables';

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function launch(action: 'reveal' | 'open', targetPath: string): boolean {
  let command: string;
  let args: string[];
  if (process.platform === 'win32') {
    command = 'explorer.exe';
    args = action === 'reveal' ? [`/select,${targetPath}`] : [targetPath];
  } else if (process.platform === 'darwin') {
    command = 'open';
    args = action === 'reveal' ? ['-R', targetPath] : [targetPath];
  } else if (process.platform === 'linux') {
    command = 'xdg-open';
    args = [targetPath];
  } else {
    return false;
  }
  // explorer.exe frequently exits non-zero even on success, so this is
  // fire-and-forget: detached + unref so the request doesn't wait on or hold
  // the server open for the launched app's lifetime.
  const child = spawn(command, args, { detached: true, stdio: 'ignore' });
  child.unref();
  return true;
}

export const POST: APIRoute = async ({ request }) => {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return json({ error: 'invalid_json' }, 400);
  }
  const { table, id, action } = (body ?? {}) as Record<string, unknown>;
  if (typeof table !== 'string' || typeof id !== 'string' || (action !== 'reveal' && action !== 'open')) {
    return json({ error: 'invalid_request' }, 400);
  }
  const spec = REVEALABLE[table];
  if (!spec) {
    return json({ error: 'unknown_table' }, 404);
  }
  const db = catalog();
  if (!db || !catalogTableNames(db).has(table)) {
    return json({ error: 'catalog_missing' }, 503);
  }
  const row = db
    .prepare(`SELECT "${spec.pathColumn}" AS path FROM "${table}" WHERE "${spec.idColumn}" = ?`)
    .get(id) as { path: string | null } | undefined;
  if (!row || !row.path || !fs.existsSync(row.path)) {
    return json({ error: 'path_not_found' }, 404);
  }
  if (!launch(action, row.path)) {
    return json({ error: 'unsupported_platform' }, 501);
  }
  return json({ status: 'ok' }, 200);
};
