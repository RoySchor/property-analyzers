import { useId } from 'react';

interface Props {
  label: string;               // e.g. "Max price"
  ceiling: number;             // highest value in the loaded data; the slider's right end
  value: number | null;        // null = no limit (thumb at the right end)
  onChange: (value: number | null) => void;
  format: (value: number) => string;
  shown: number;
  total: number;
  noun: string;                // "listings", "sales", "parcels"
}

/** Rounds the step so the slider moves in friendly increments ($1k, $2.5k, $5k…) for any range. */
function niceStep(ceiling: number): number {
  const raw = ceiling / 100;
  if (raw <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const normalized = raw / magnitude;
  const nice = normalized <= 1 ? 1 : normalized <= 2.5 ? 2.5 : normalized <= 5 ? 5 : 10;
  return nice * magnitude;
}

/**
 * Drag left to hide rows above a value. Every piece of text keeps a fixed width so the track never
 * shifts under the cursor while dragging (that shift was what made the ends jumpy).
 */
export default function MaxSlider({ label, ceiling, value, onChange, format, shown, total, noun }: Props) {
  const id = useId();
  const step = niceStep(ceiling);
  // The track's top is rounded up to a whole step so the thumb can always reach the far right.
  const top = Math.max(step, Math.ceil(ceiling / step) * step);
  const current = value === null ? top : Math.min(value, top);
  const displayed = value === null ? ceiling : Math.min(value, ceiling);

  return (
    <div className="w-72 shrink-0 rounded-md border border-gray-200 px-3 py-1.5 dark:border-gray-700">
      <div className="flex items-center justify-between text-xs">
        <label htmlFor={id} className="text-gray-600 dark:text-gray-300">{label}</label>
        <span className="flex items-center gap-2">
          <span className="tabular w-14 text-right font-semibold text-gray-900 dark:text-gray-100">{format(displayed)}</span>
          <button
            type="button"
            onClick={() => onChange(null)}
            className={`w-9 text-right text-blue-600 hover:underline dark:text-blue-400 ${value === null ? 'invisible' : ''}`}
            tabIndex={value === null ? -1 : 0}
          >
            Reset
          </button>
        </span>
      </div>
      <input
        id={id}
        type="range"
        min={0}
        max={top}
        step={step}
        value={current}
        disabled={ceiling <= 0}
        onChange={(e) => {
          const next = Number(e.target.value);
          onChange(next >= ceiling ? null : next);
        }}
        className="my-1 block h-1.5 w-full cursor-pointer accent-blue-600"
      />
      <div className="tabular flex items-center justify-between text-[0.625rem] leading-none text-gray-500 dark:text-gray-400">
        <span>$0</span>
        <span title={`${noun} shown out of total ${noun} loaded`}>
          {shown} / {total} {noun} shown
        </span>
        <span>{format(ceiling)}</span>
      </div>
    </div>
  );
}
