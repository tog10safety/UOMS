import { useEffect, useState } from 'react';

import { reportsApi } from '@/api/endpoints';
import type { ReportData, ReportListItem, ReportType } from '@/types';

export default function Reports() {
  const [reportTypes, setReportTypes] = useState<ReportListItem[]>([]);
  const [selected, setSelected] = useState<ReportType | null>(null);
  const [data, setData] = useState<ReportData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isExporting, setIsExporting] = useState<'pdf' | 'xlsx' | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    reportsApi
      .list()
      .then((types) => {
        setReportTypes(types);
        if (types.length > 0) setSelected(types[0].type);
      })
      .catch(() => setError('Unable to load report types.'))
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    if (!selected) return;
    setIsLoading(true);
    reportsApi
      .get(selected)
      .then((d) => setData(d))
      .catch(() => setError('Unable to load report data.'))
      .finally(() => setIsLoading(false));
  }, [selected]);

  const handleExport = async (format: 'pdf' | 'xlsx') => {
    if (!selected) return;
    setIsExporting(format);
    try {
      await reportsApi.download(selected, format);
    } catch {
      setError('Export failed.');
    } finally {
      setIsExporting(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          {reportTypes.map((rt) => (
            <button
              key={rt.type}
              onClick={() => setSelected(rt.type)}
              className={`rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
                selected === rt.type
                  ? 'border-ops-accent bg-ops-accent/10 text-ops-accent'
                  : 'border-ops-border text-ops-textDim hover:text-ops-text'
              }`}
            >
              {rt.label}
            </button>
          ))}
        </div>

        <div className="flex gap-2">
          <button
            disabled={!selected || isExporting !== null}
            onClick={() => handleExport('pdf')}
            className="rounded-md border border-ops-border px-3 py-1.5 text-xs font-medium text-ops-text hover:border-ops-accent hover:text-ops-accent disabled:opacity-50"
          >
            {isExporting === 'pdf' ? 'Exporting…' : 'Export PDF'}
          </button>
          <button
            disabled={!selected || isExporting !== null}
            onClick={() => handleExport('xlsx')}
            className="rounded-md border border-ops-border px-3 py-1.5 text-xs font-medium text-ops-text hover:border-ops-accent hover:text-ops-accent disabled:opacity-50"
          >
            {isExporting === 'xlsx' ? 'Exporting…' : 'Export Excel'}
          </button>
        </div>
      </div>

      {error && <p className="text-sm text-ops-danger">{error}</p>}

      <div className="ops-card overflow-hidden">
        {data && (
          <div className="flex items-center justify-between border-b border-ops-border px-4 py-3">
            <p className="text-sm font-semibold text-ops-text">{data.title}</p>
            <span className="text-xs text-ops-textDim">{data.row_count} record(s)</span>
          </div>
        )}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            {data && (
              <thead className="bg-ops-panelLight text-xs uppercase tracking-wider text-ops-textDim">
                <tr>
                  {data.headers.map((h) => (
                    <th key={h} className="whitespace-nowrap px-4 py-2">{h}</th>
                  ))}
                </tr>
              </thead>
            )}
            <tbody>
              {!isLoading && data && data.rows.length === 0 && (
                <tr>
                  <td colSpan={data.headers.length} className="px-4 py-6 text-center text-ops-textDim">
                    No records found.
                  </td>
                </tr>
              )}
              {data?.rows.map((row, idx) => (
                <tr key={idx} className="border-t border-ops-border hover:bg-ops-panelLight/50">
                  {row.map((cell, cellIdx) => (
                    <td key={cellIdx} className="whitespace-nowrap px-4 py-2 text-ops-text">{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
