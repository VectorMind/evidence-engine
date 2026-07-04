/**
 * Server-driven data table island (plan D5).
 *
 * TanStack React Table in fully manual mode: pagination, sorting, and the
 * global filter are all resolved server-side by /api/table/<name>.json —
 * the client holds exactly one page. The server SSRs page 1 into the
 * island's props so first paint shows data without a fetch.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
  type SortingState,
} from '@tanstack/react-table';
import './table.css';

export interface DataTableColumn {
  key: string;
  label: string;
  sortable?: boolean;
  kind?: 'text' | 'number' | 'timestamp';
}

export interface DataTableProps {
  endpoint: string;
  columns: DataTableColumn[];
  initialRows: Record<string, unknown>[];
  initialTotal: number;
  defaultSort: { col: string; dir: 'asc' | 'desc' };
  pageSizes: number[];
  defaultPageSize: number;
}

type Row = Record<string, unknown>;

function formatCell(value: unknown, kind?: string): string {
  if (value === null || value === undefined) {
    return '';
  }
  if (kind === 'number' && typeof value === 'number') {
    return value.toLocaleString('en-US');
  }
  return String(value);
}

export default function DataTable({
  endpoint,
  columns,
  initialRows,
  initialTotal,
  defaultSort,
  pageSizes,
  defaultPageSize,
}: DataTableProps) {
  const [rows, setRows] = useState<Row[]>(initialRows);
  const [total, setTotal] = useState(initialTotal);
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState(defaultPageSize);
  const [sorting, setSorting] = useState<SortingState>([
    { id: defaultSort.col, desc: defaultSort.dir === 'desc' },
  ]);
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const firstRender = useRef(true);

  // Debounce typed search into the applied query.
  useEffect(() => {
    const handle = window.setTimeout(() => {
      setQuery(search);
      setPageIndex(0);
    }, 300);
    return () => window.clearTimeout(handle);
  }, [search]);

  useEffect(() => {
    // Page 1 with default state was SSR'd into the props; only fetch on change.
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    const sort = sorting[0] ?? { id: defaultSort.col, desc: defaultSort.dir === 'desc' };
    const params = new URLSearchParams({
      limit: String(pageSize),
      offset: String(pageIndex * pageSize),
      sort: sort.id,
      dir: sort.desc ? 'desc' : 'asc',
    });
    if (query !== '') {
      params.set('q', query);
    }
    const controller = new AbortController();
    setLoading(true);
    setError('');
    fetch(`${endpoint}?${params.toString()}`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`request failed (${response.status})`);
        }
        const payload = await response.json();
        setRows(payload.rows);
        setTotal(payload.total);
      })
      .catch((cause: unknown) => {
        if (!(cause instanceof DOMException && cause.name === 'AbortError')) {
          setError(cause instanceof Error ? cause.message : String(cause));
        }
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [endpoint, pageIndex, pageSize, sorting, query, defaultSort.col, defaultSort.dir]);

  const helper = createColumnHelper<Row>();
  const tableColumns = useMemo(
    () =>
      columns.map((column) =>
        helper.accessor((row) => row[column.key], {
          id: column.key,
          header: column.label,
          enableSorting: Boolean(column.sortable),
          cell: (info) => formatCell(info.getValue(), column.kind),
        }),
      ),
    [columns],
  );

  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const table = useReactTable({
    data: rows,
    columns: tableColumns,
    state: { sorting, pagination: { pageIndex, pageSize } },
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    pageCount,
    rowCount: total,
    onSortingChange: (updater) => {
      setSorting(updater);
      setPageIndex(0);
    },
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="data-table">
      <div className="data-table-toolbar">
        <input
          type="search"
          className="data-table-search"
          placeholder="Filter..."
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          aria-label="Filter rows"
        />
        <span className="data-table-status">
          {loading ? 'Loading...' : `${total.toLocaleString('en-US')} rows`}
          {error !== '' && <span className="data-table-error"> {error}</span>}
        </span>
      </div>
      <div className="data-table-scroll">
        <table>
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  const sorted = header.column.getIsSorted();
                  return (
                    <th
                      key={header.id}
                      className={header.column.getCanSort() ? 'sortable' : ''}
                      onClick={header.column.getToggleSortingHandler()}
                    >
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {sorted === 'asc' && <span className="sort-mark"> ▲</span>}
                      {sorted === 'desc' && <span className="sort-mark"> ▼</span>}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id}>
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td className="data-table-empty" colSpan={columns.length}>
                  No rows.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="data-table-pager">
        <button
          type="button"
          onClick={() => setPageIndex(0)}
          disabled={pageIndex === 0}
        >
          «
        </button>
        <button
          type="button"
          onClick={() => setPageIndex(pageIndex - 1)}
          disabled={pageIndex === 0}
        >
          ‹
        </button>
        <span>
          Page {pageIndex + 1} of {pageCount}
        </span>
        <button
          type="button"
          onClick={() => setPageIndex(pageIndex + 1)}
          disabled={pageIndex + 1 >= pageCount}
        >
          ›
        </button>
        <button
          type="button"
          onClick={() => setPageIndex(pageCount - 1)}
          disabled={pageIndex + 1 >= pageCount}
        >
          »
        </button>
        <select
          value={pageSize}
          onChange={(event) => {
            setPageSize(Number(event.target.value));
            setPageIndex(0);
          }}
          aria-label="Rows per page"
        >
          {pageSizes.map((size) => (
            <option key={size} value={size}>
              {size} / page
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
