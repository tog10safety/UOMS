import { useEffect, useMemo, useRef, useState } from 'react';

export interface SearchableOption {
  value: string;
  label: string;
  sublabel?: string;
}

interface SearchableSelectProps {
  options: SearchableOption[];
  value: string | null;
  onChange: (value: string | null) => void;
  placeholder?: string;
  emptyLabel?: string;
  disabled?: boolean;
  /** Draws the control in its error state (the message itself is rendered by the field wrapper). */
  invalid?: boolean;
}

export default function SearchableSelect({
  options,
  value,
  onChange,
  placeholder = 'Select…',
  emptyLabel = '— Clear selection —',
  disabled = false,
  invalid = false,
}: SearchableSelectProps) {
  const [query, setQuery] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const selected = options.find((o) => o.value === value) ?? null;

  const filtered = useMemo(() => {
    if (!query.trim()) return options;
    const q = query.toLowerCase();
    return options.filter((o) => o.label.toLowerCase().includes(q) || o.sublabel?.toLowerCase().includes(q));
  }, [options, query]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
        setQuery('');
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setIsOpen((o) => !o)}
        className={`flex w-full items-center justify-between rounded-md border bg-ops-panelLight px-3 py-2 text-left text-sm text-ops-text outline-none focus:border-ops-accent disabled:opacity-50 ${invalid ? 'border-ops-danger' : 'border-ops-border'}`}
      >
        <span className={selected ? 'text-ops-text' : 'text-ops-textDim'}>
          {selected ? selected.label : placeholder}
        </span>
        <span className="text-ops-textDim">▾</span>
      </button>

      {isOpen && (
        <div className="absolute z-20 mt-1 w-full rounded-md border border-ops-border bg-ops-panel shadow-xl">
          <input
            autoFocus
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Type to search…"
            className="w-full border-b border-ops-border bg-transparent px-3 py-2 text-sm text-ops-text outline-none"
          />
          <div className="max-h-56 overflow-y-auto">
            {selected && (
              <button
                type="button"
                onClick={() => {
                  onChange(null);
                  setIsOpen(false);
                  setQuery('');
                }}
                className="block w-full px-3 py-2 text-left text-sm text-ops-textDim hover:bg-ops-panelLight"
              >
                {emptyLabel}
              </button>
            )}
            {filtered.length === 0 && (
              <p className="px-3 py-2 text-xs text-ops-textDim">No matches.</p>
            )}
            {filtered.map((o) => (
              <button
                key={o.value}
                type="button"
                onClick={() => {
                  onChange(o.value);
                  setIsOpen(false);
                  setQuery('');
                }}
                className={`block w-full px-3 py-2 text-left text-sm hover:bg-ops-panelLight ${
                  o.value === value ? 'bg-ops-accent/10 text-ops-accent' : 'text-ops-text'
                }`}
              >
                {o.label}
                {o.sublabel && <span className="ml-2 text-xs text-ops-textDim">{o.sublabel}</span>}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
