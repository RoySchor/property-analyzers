import { useState } from 'react';
import { api } from '../api/client';
import { Card, ErrorBanner, Loading } from '../components/ui';
import { buttonClass, inputClass } from '../components/styles';
import { useAsync } from '../components/useAsync';

const FIELDS: { key: string; label: string; hint?: string }[] = [
  { key: 'max_price', label: 'Max price ($)', hint: 'Listings, deals and comps are capped here' },
  { key: 'min_price', label: 'Min price ($)' },
  { key: 'down_payment_pct', label: 'Down payment (%)' },
  { key: 'interest_rate_pct', label: 'Interest rate (%)', hint: 'Blank = latest 30-yr rate + investor premium' },
  { key: 'investor_rate_premium_pct', label: 'Investor rate premium (%)' },
  { key: 'loan_years', label: 'Loan term (years)' },
  { key: 'closing_cost_pct', label: 'Closing costs (%)' },
  { key: 'vacancy_pct', label: 'Vacancy (% of rent)' },
  { key: 'maintenance_pct', label: 'Maintenance (% of rent)' },
  { key: 'capex_pct', label: 'CapEx reserve (% of rent)' },
  { key: 'management_pct', label: 'Property management (% of rent)' },
  { key: 'insurance_annual', label: 'Insurance ($/year)' },
  { key: 'fallback_tax_rate_pct', label: 'Fallback tax rate (% of price)', hint: 'Used when county millage is unknown' },
];

export default function Settings() {
  const { data, error, loading, reload } = useAsync(() => api.settings(), []);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const values = { ...(data?.settings ?? {}), ...edits };

  if (loading) return <Loading />;

  const save = async () => {
    setSaveError(null);
    setSaved(false);
    try {
      const changed = Object.fromEntries(FIELDS.map((f) => [f.key, values[f.key] ?? '']));
      await api.updateSettings(changed);
      setSaved(true);
      setEdits({});
      reload();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <Card
      title="Investment assumptions"
      subtitle={`Current effective rate: ${data?.effective_interest_rate_pct ?? '—'}% · RentCast used ${data?.rentcast.used ?? 0}/${data?.rentcast.cap ?? 0} in the last 31 days (hard limit). Saving recalculates every score. Raising the max price pulls the new listings on the next sync.`}
    >
      {error && <ErrorBanner message={error} onRetry={reload} />}
      {saveError && <ErrorBanner message={saveError} />}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {FIELDS.map((field) => (
          <label key={field.key} className="block text-sm text-gray-700 dark:text-gray-200">
            {field.label}
            <input
              className={`${inputClass} tabular mt-1 w-full`}
              inputMode="decimal"
              value={values[field.key] ?? ''}
              onChange={(e) => setEdits({ ...edits, [field.key]: e.target.value })}
            />
            {field.hint && <span className="text-xs text-gray-500 dark:text-gray-400">{field.hint}</span>}
          </label>
        ))}
      </div>
      <div className="mt-4 flex items-center gap-3">
        <button className={buttonClass} onClick={save}>Save & recalculate</button>
        {saved && <span className="text-sm text-green-700 dark:text-green-400">Saved ✓</span>}
      </div>
    </Card>
  );
}
