import type { ReactNode } from 'react';

interface ModalProps {
  title: string;
  onClose?: () => void;
  children: ReactNode;
  width?: 'sm' | 'md' | 'lg' | 'xl';
}

const WIDTHS = { sm: 'max-w-sm', md: 'max-w-lg', lg: 'max-w-2xl', xl: 'max-w-4xl' };

export default function Modal({ title, onClose, children, width = 'md' }: ModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className={`ops-card max-h-[90vh] w-full ${WIDTHS[width]} space-y-3 overflow-y-auto p-6`}>
        <div className="flex items-center justify-between">
          <p className="ops-label">{title}</p>
          {onClose && (
            <button type="button" onClick={onClose} className="text-sm text-ops-textDim hover:text-ops-text" aria-label="Close">
              ✕
            </button>
          )}
        </div>
        {children}
      </div>
    </div>
  );
}
