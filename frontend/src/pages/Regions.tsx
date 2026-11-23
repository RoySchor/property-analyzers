import { useState } from 'react';
import { api, type Region } from '../api/client';
import { Card, ErrorBanner, Loading } from '../components/ui';
import { buttonClass, ghostButtonClass, inputClass } from '../components/styles';
import { useAsync } from '../components/useAsync';

interface Draft {
  id?: number;
  name: string;
  zips: string;
  counties: string[];
  is_active: boolean;
}

const emptyDraft: Draft = { name: '', zips: '', counties: [], is_active: true };

export default function Regions() {
  const { data, error, loading, reload } = useAsync(() => api.regions(), []);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  if (loading) return <Loading />;
  const supported = data?.supported_counties ?? {};

  const edit = (region: Region) =>
    setDraft({ id: region.id, name: region.name, zips: region.zips.join(', '), counties: region.counties, is_active: region.is_active });

  const save = async () => {
    setSaving(true);
    setSaveError(null);
    const body = {
      name: draft.name,
      zips: draft.zips.split(/[\s,]+/).filter(Boolean),
      counties: draft.counties,
      is_active: draft.is_active,
    };
    try {
      if (draft.id) await api.updateRegion(draft.id, body);
      else await api.createRegion(body);
      setDraft(emptyDraft);
      reload();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (region: Region) => {
    try {
      await api.updateRegion(region.id, { ...region, is_active: !region.is_active });
      reload();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : String(e));
    }
  };

  const remove = async (region: Region) => {
    try {
      await api.deleteRegion(region.id);
      reload();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title="Your areas" subtitle="Every active area's ZIPs are pulled on each sync. Adding or editing one starts a sync.">
        {error && <ErrorBanner message={error} onRetry={reload} />}
        <ul className="divide-y divide-gray-100 dark:divide-gray-700">
          {data?.regions.map((region) => (
            <li key={region.id} className="flex items-center justify-between gap-3 py-3">
              <div>
                <div className="font-medium text-gray-900 dark:text-gray-100">
                  {region.name} {region.is_default && <span className="ml-1 rounded bg-blue-100 px-1.5 py-0.5 text-xs text-blue-700 dark:bg-blue-900 dark:text-blue-300">default</span>}
                  {!region.is_active && <span className="ml-1 text-xs text-gray-500">(paused)</span>}
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400">
                  ZIPs {region.zips.join(', ')} · parcels from {region.counties.map((c) => supported[c] ?? c).join(' + ') || 'none'}
                </div>
              </div>
              <div className="flex gap-2">
                <button className={ghostButtonClass} onClick={() => edit(region)}>Edit</button>
                <button className={ghostButtonClass} onClick={() => toggleActive(region)}>{region.is_active ? 'Pause' : 'Resume'}</button>
                {!region.is_default && <button className={ghostButtonClass} onClick={() => remove(region)}>Delete</button>}
              </div>
            </li>
          ))}
        </ul>
      </Card>

      <Card title={draft.id ? `Edit ${draft.name}` : 'Add an area'} subtitle="Market trends, listings and sold data work for any US ZIP. County sale history and real taxes need a supported county.">
        {saveError && <ErrorBanner message={saveError} />}
        <div className="space-y-3">
          <label className="block text-sm text-gray-700 dark:text-gray-200">
            Name
            <input className={`${inputClass} mt-1 w-full`} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="Allentown" />
          </label>
          <label className="block text-sm text-gray-700 dark:text-gray-200">
            ZIP codes
            <input className={`${inputClass} mt-1 w-full`} value={draft.zips} onChange={(e) => setDraft({ ...draft, zips: e.target.value })} placeholder="18101, 18102, 18103" />
          </label>
          <fieldset className="text-sm text-gray-700 dark:text-gray-200">
            <legend>County parcel data</legend>
            <div className="mt-1 flex gap-4">
              {Object.entries(supported).map(([fips, name]) => (
                <label key={fips} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={draft.counties.includes(fips)}
                    onChange={(e) =>
                      setDraft({ ...draft, counties: e.target.checked ? [...draft.counties, fips] : draft.counties.filter((c) => c !== fips) })
                    }
                  />
                  {name}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="flex gap-2">
            <button className={buttonClass} disabled={saving} onClick={save}>{saving ? 'Saving…' : draft.id ? 'Save changes' : 'Add area'}</button>
            {draft.id && <button className={ghostButtonClass} onClick={() => setDraft(emptyDraft)}>Cancel</button>}
          </div>
        </div>
      </Card>
    </div>
  );
}
