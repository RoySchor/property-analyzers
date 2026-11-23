import { useId, useState, type KeyboardEvent } from 'react';

export interface Suggestion {
  value: string;
  hint?: string;   // e.g. "owner"
}

interface Props {
  value: string;
  onChange: (value: string) => void;
  suggestions: Suggestion[];
  placeholder: string;
  maxSuggestions?: number;
}

/**
 * Text input with a live suggestion list. Suggestions narrow as you type (the caller filters by the query);
 * pick one with click, or ↑/↓ + Enter. Esc closes the list.
 */
export default function SearchBox({ value, onChange, suggestions, placeholder, maxSuggestions = 8 }: Props) {
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(-1);
  const listId = useId();

  const query = value.trim().toLowerCase();
  const visible = query
    ? suggestions
        .filter((s) => s.value.toLowerCase().includes(query) && s.value.toLowerCase() !== query)
        .slice(0, maxSuggestions)
    : [];
  const showList = open && visible.length > 0;

  const choose = (suggestion: Suggestion) => {
    onChange(suggestion.value);
    setOpen(false);
    setHighlight(-1);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Escape') {
      setOpen(false);
      return;
    }
    if (!showList) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setHighlight((h) => (h + 1) % visible.length);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setHighlight((h) => (h <= 0 ? visible.length - 1 : h - 1));
    } else if (event.key === 'Enter' && highlight >= 0) {
      event.preventDefault();
      choose(visible[highlight]);
    }
  };

  return (
    <div className="relative w-full max-w-sm">
      <input
        type="search"
        role="combobox"
        aria-expanded={showList}
        aria-controls={listId}
        aria-autocomplete="list"
        value={value}
        placeholder={placeholder}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
          setHighlight(-1);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)} // let a click on a suggestion land first
        onKeyDown={onKeyDown}
        className="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 placeholder:text-gray-400 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
      />
      {showList && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-20 mt-1 max-h-72 w-full overflow-auto rounded-md border border-gray-200 bg-white py-1 text-sm shadow-lg dark:border-gray-600 dark:bg-gray-800"
        >
          {visible.map((suggestion, index) => (
            <li
              key={`${suggestion.hint ?? ''}${suggestion.value}`}
              role="option"
              aria-selected={index === highlight}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => choose(suggestion)}
              onMouseEnter={() => setHighlight(index)}
              className={`flex cursor-pointer items-center justify-between gap-2 px-3 py-1.5 ${
                index === highlight ? 'bg-blue-50 text-blue-800 dark:bg-blue-900/50 dark:text-blue-200' : 'text-gray-800 dark:text-gray-200'
              }`}
            >
              <span className="truncate">{suggestion.value}</span>
              {suggestion.hint && <span className="shrink-0 text-xs text-gray-500 dark:text-gray-400">{suggestion.hint}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
