/**
 * Renders a `kind: 'path'` cell as a clickable pill (plan D5 follow-up).
 * Clicking the pill reveals the item in the OS file explorer; a second,
 * distinct icon segment — shown only for files, since opening a folder is
 * the same action as revealing it — opens the file with its default app.
 * Both actions POST to /api/reveal.json, which resolves the absolute path
 * server-side from `table` + `id` (see lib/tables.ts REVEALABLE).
 */
import { useState } from 'react';

export interface PathPillProps {
  path: string;
  itemKind: string;
  table: string;
  id: string;
}

type Status = 'idle' | 'pending' | 'error';

async function trigger(table: string, id: string, action: 'reveal' | 'open'): Promise<boolean> {
  try {
    const response = await fetch('/api/reveal.json', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ table, id, action }),
    });
    return response.ok;
  } catch {
    return false;
  }
}

export default function PathPill({ path, itemKind, table, id }: PathPillProps) {
  const [status, setStatus] = useState<Status>('idle');
  const name = path.split('/').filter(Boolean).pop() ?? path;
  const isFile = itemKind === 'file';

  async function run(action: 'reveal' | 'open') {
    if (!id) {
      return;
    }
    setStatus('pending');
    const ok = await trigger(table, id, action);
    setStatus(ok ? 'idle' : 'error');
  }

  return (
    <span className={`path-pill${status === 'error' ? ' path-pill-error' : ''}`} title={path}>
      <button
        type="button"
        className="path-pill-main"
        onClick={() => run('reveal')}
        disabled={status === 'pending'}
        aria-label={`Reveal ${path} in file explorer`}
      >
        <span className="path-pill-icon" aria-hidden="true">
          {isFile ? '📄' : '📁'}
        </span>
        <span className="path-pill-name">{name}</span>
      </button>
      {isFile && (
        <button
          type="button"
          className="path-pill-open"
          onClick={() => run('open')}
          disabled={status === 'pending'}
          aria-label={`Open ${path} with its default app`}
          title="Open with default app"
        >
          ↗
        </button>
      )}
    </span>
  );
}
