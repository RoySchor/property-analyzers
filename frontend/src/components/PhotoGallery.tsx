import { useState } from 'react';

/** Large photo with thumbnails underneath. Photos are hot-linked from Realtor.com's image CDN. */
export default function PhotoGallery({ photos, alt }: { photos: string[]; alt: string }) {
  const [index, setIndex] = useState(0);
  const [failed, setFailed] = useState<Set<string>>(new Set());
  const usable = photos.filter((url) => !failed.has(url));

  if (!usable.length) {
    return (
      <div className="flex h-48 items-center justify-center rounded-xl border border-dashed border-gray-300 text-sm text-gray-500 dark:border-gray-600 dark:text-gray-400">
        No photos for this listing yet — they load on the next listings sync.
      </div>
    );
  }

  const current = Math.min(index, usable.length - 1);
  const markFailed = (url: string) => setFailed((prev) => new Set(prev).add(url));
  const step = (delta: number) => setIndex((current + delta + usable.length) % usable.length);

  return (
    <div className="space-y-2">
      <div className="relative overflow-hidden rounded-xl bg-gray-100 dark:bg-gray-800">
        <img
          src={usable[current]}
          alt={`${alt} — photo ${current + 1} of ${usable.length}`}
          onError={() => markFailed(usable[current])}
          className="mx-auto max-h-[28rem] w-full object-contain"
        />
        {usable.length > 1 && (
          <>
            <button
              onClick={() => step(-1)}
              aria-label="Previous photo"
              className="absolute left-2 top-1/2 -translate-y-1/2 rounded-full bg-black/50 px-3 py-1 text-lg text-white hover:bg-black/70"
            >
              ‹
            </button>
            <button
              onClick={() => step(1)}
              aria-label="Next photo"
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full bg-black/50 px-3 py-1 text-lg text-white hover:bg-black/70"
            >
              ›
            </button>
            <span className="absolute bottom-2 right-2 rounded bg-black/60 px-2 py-0.5 text-xs text-white">
              {current + 1} / {usable.length}
            </span>
          </>
        )}
      </div>
      {usable.length > 1 && (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {usable.map((url, i) => (
            <button
              key={url}
              onClick={() => setIndex(i)}
              aria-label={`Show photo ${i + 1}`}
              className={`h-16 w-24 shrink-0 overflow-hidden rounded-md border-2 ${
                i === current ? 'border-blue-500' : 'border-transparent opacity-70 hover:opacity-100'
              }`}
            >
              <img src={url} alt="" loading="lazy" onError={() => markFailed(url)} className="h-full w-full object-cover" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
