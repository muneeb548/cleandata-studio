import { useEffect, useState, type ReactNode } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Search, SearchX, X } from "lucide-react";
import { api } from "@/api/client";
import type { DatasetKind, RowsPage } from "@/api/types";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select } from "@/components/ui/form";
import { EmptyState, LoadingBlock, Spinner } from "@/components/ui/misc";
import { PageHeader } from "@/components/ui/page";
import { RowNumberCell, Table, TableContainer, TD, TH, THead, TR } from "@/components/ui/table";
import { cn, formatNumber } from "@/lib/utils";
import { Cell, DatasetToggle, TypeBadge } from "./shared";
import { useAsync } from "./useAsync";
import { useWorkspace } from "./WorkspaceContext";

type Sort = { column: string; dir: "asc" | "desc" } | null;

/** Read-only grid for a page of rows. Used by the data view, previews and comparisons. */
export function RowsTable({
  columns,
  rows,
  rowNumbers,
  sort,
  onSort,
  caption,
  maxHeight = "max-h-[62vh]",
  rowClassName,
  renderCell,
}: {
  columns: { name: string; type?: RowsPage["columns"][number]["type"] }[];
  rows: RowsPage["rows"];
  rowNumbers: number[];
  sort?: Sort;
  onSort?: (column: string) => void;
  caption: string;
  maxHeight?: string;
  rowClassName?: (index: number) => string | undefined;
  renderCell?: (rowIndex: number, colIndex: number) => ReactNode | undefined;
}) {
  return (
    <TableContainer label={caption} maxHeight={maxHeight}>
      <Table className="w-max min-w-full">
        <caption className="sr-only">{caption}</caption>
        <THead>
          <tr>
            <TH scope="col" className="sticky left-0 z-20 border-r text-right">
              #
            </TH>
            {columns.map((col) => {
              const active = sort?.column === col.name;
              const SortIcon = !active ? ArrowUpDown : sort!.dir === "asc" ? ArrowUp : ArrowDown;
              return (
                <TH key={col.name} scope="col" aria-sort={active ? (sort!.dir === "asc" ? "ascending" : "descending") : undefined}>
                  {onSort ? (
                    <button
                      type="button"
                      onClick={() => onSort(col.name)}
                      className="group -mx-1 flex min-h-6 max-w-60 items-center gap-1.5 rounded px-1 text-left text-small font-semibold text-slate-800 hover:text-primary"
                    >
                      <span className="truncate" title={col.name}>
                        {col.name}
                      </span>
                      <SortIcon className={cn("size-3.5 shrink-0", active ? "text-primary" : "text-slate-300 group-hover:text-slate-500")} aria-hidden="true" />
                      <span className="sr-only">Sort by {col.name}</span>
                    </button>
                  ) : (
                    <span className="block max-w-60 truncate text-small font-semibold text-slate-800" title={col.name}>
                      {col.name}
                    </span>
                  )}
                  {col.type && <TypeBadge type={col.type} className="mt-0.5" />}
                </TH>
              );
            })}
          </tr>
        </THead>
        <tbody>
          {rows.map((row, i) => (
            <TR key={`${rowNumbers[i]}-${i}`} className={rowClassName?.(i)}>
              <RowNumberCell>{rowNumbers[i]}</RowNumberCell>
              {row.map((value, j) => (
                <TD key={j} className="max-w-72 py-1.5">
                  {renderCell?.(i, j) ?? <Cell value={value} />}
                </TD>
              ))}
            </TR>
          ))}
        </tbody>
      </Table>
    </TableContainer>
  );
}

export function Pagination({ page, totalPages, onPage }: { page: number; totalPages: number; onPage: (p: number) => void }) {
  return (
    <nav aria-label="Pagination" className="flex items-center gap-1">
      <Button variant="ghost" size="icon" className="size-8" disabled={page <= 1} onClick={() => onPage(1)} aria-label="First page">
        <ChevronsLeft />
      </Button>
      <Button variant="ghost" size="icon" className="size-8" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Previous page">
        <ChevronLeft />
      </Button>
      <span className="tabular px-2 text-small text-slate-600">
        Page {formatNumber(page)} of {formatNumber(totalPages)}
      </span>
      <Button variant="ghost" size="icon" className="size-8" disabled={page >= totalPages} onClick={() => onPage(page + 1)} aria-label="Next page">
        <ChevronRight />
      </Button>
      <Button variant="ghost" size="icon" className="size-8" disabled={page >= totalPages} onClick={() => onPage(totalPages)} aria-label="Last page">
        <ChevronsRight />
      </Button>
    </nav>
  );
}

export function DataPanel() {
  const { version, info } = useWorkspace();
  const [dataset, setDataset] = useState<DatasetKind>("current");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(100);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<Sort>(null);

  // Debounce typing so the server is not queried on every keystroke.
  useEffect(() => {
    const t = window.setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(1);
    }, 300);
    return () => window.clearTimeout(t);
  }, [searchInput]);

  useEffect(() => {
    setPage(1);
    setSort(null);
  }, [dataset, version]);

  const { data, error, loading, reload } = useAsync(
    () => api.rows({ dataset, page, pageSize, search, sortBy: sort?.column, sortDir: sort?.dir }),
    [dataset, page, pageSize, search, sort, version],
    version,
  );

  const toggleSort = (column: string) => {
    setPage(1);
    setSort((s) => (s?.column !== column ? { column, dir: "asc" } : s.dir === "asc" ? { column, dir: "desc" } : null));
  };

  const shape = info ? (dataset === "original" ? info.original_shape : info.current_shape) : null;
  const start = data ? (data.page - 1) * data.page_size + 1 : 0;
  const end = data ? start + data.rows.length - 1 : 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Data preview"
        description={
          shape
            ? `${formatNumber(shape.rows)} rows × ${formatNumber(shape.columns)} columns. Row numbers refer to the position in the uploaded file.`
            : undefined
        }
        actions={<DatasetToggle value={dataset} onChange={setDataset} />}
      />

      <Card className="overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-border px-4 py-3 sm:flex-row sm:items-center">
          <div className="relative flex-1 sm:max-w-sm">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-slate-500" aria-hidden="true" />
            <input
              type="search"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search all columns"
              aria-label="Search all columns"
              className="h-9 w-full rounded-md border border-border-strong pr-8 pl-8 text-body placeholder:text-slate-500 focus-visible:border-primary"
            />
            {searchInput && (
              <button
                type="button"
                onClick={() => setSearchInput("")}
                className="absolute top-1/2 right-2 -translate-y-1/2 rounded p-0.5 text-slate-500 hover:text-slate-700"
                aria-label="Clear search"
              >
                <X className="size-4" />
              </button>
            )}
          </div>
          <div className="flex items-center gap-3 sm:ml-auto">
            {loading && data && <Spinner label="Updating" />}
            {sort && (
              <Button variant="ghost" size="sm" onClick={() => setSort(null)}>
                Clear sort
              </Button>
            )}
            <label htmlFor="page-size" className="text-small whitespace-nowrap text-muted-foreground">
              Rows per page
            </label>
            <div className="w-24">
              <Select
                id="page-size"
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value));
                  setPage(1);
                }}
              >
                <option value={50}>50</option>
                <option value={100}>100</option>
                <option value={200}>200</option>
              </Select>
            </div>
          </div>
        </div>

        {error && !data && (
          <div className="p-4">
            <Alert tone="danger" title={error.message} action={<Button size="sm" variant="secondary" onClick={reload}>Retry</Button>}>
              {error.hint}
            </Alert>
          </div>
        )}
        {!data && loading && <LoadingBlock label="Loading rows…" />}

        {data && data.columns.length === 0 && (
          <EmptyState title="This dataset has no columns">All columns have been removed. Use Undo or Reset to restore them.</EmptyState>
        )}
        {data && data.columns.length > 0 && data.rows.length === 0 && (
          <EmptyState
            icon={<SearchX />}
            title={search ? "No rows match your search" : "This dataset has no rows"}
            action={search ? <Button variant="secondary" size="sm" onClick={() => setSearchInput("")}>Clear search</Button> : undefined}
          >
            {search ? `Nothing contains “${search}”.` : "The file has column headers but no data rows."}
          </EmptyState>
        )}
        {data && data.rows.length > 0 && (
          <RowsTable
            columns={data.columns}
            rows={data.rows}
            rowNumbers={data.row_numbers}
            sort={sort}
            onSort={toggleSort}
            caption={`${dataset === "original" ? "Original" : "Working"} data, page ${data.page} of ${data.total_pages}`}
          />
        )}

        {data && data.total_rows > 0 && (
          <div className="flex flex-col items-center justify-between gap-3 border-t border-border bg-canvas px-4 py-2.5 sm:flex-row">
            <p className="tabular text-small text-muted-foreground" aria-live="polite">
              Showing {formatNumber(start)}–{formatNumber(end)} of {formatNumber(data.total_rows)} rows
              {search && ` (filtered from ${formatNumber(data.unfiltered_rows)})`}
            </p>
            <Pagination page={data.page} totalPages={data.total_pages} onPage={setPage} />
          </div>
        )}
      </Card>
    </div>
  );
}
