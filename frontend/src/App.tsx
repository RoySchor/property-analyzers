import { useEffect, useState } from 'react';
import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom';
import SyncBar from './components/SyncBar';
import Dashboard from './pages/Dashboard';
import Garages from './pages/Garages';
import ListingDetail from './pages/ListingDetail';
import Listings from './pages/Listings';
import Regions from './pages/Regions';
import PropertyDetail from './pages/PropertyDetail';
import Sales from './pages/Sales';
import Settings from './pages/Settings';
import SyncStatus from './pages/SyncStatus';
import Watchlist from './pages/Watchlist';

const navItems = [
  { to: '/', label: 'Trends' },
  { to: '/listings', label: 'Listings' },
  { to: '/sales', label: 'Sales' },
  { to: '/garages', label: 'Garages' },
  { to: '/watchlist', label: 'Watchlist' },
  { to: '/regions', label: 'My Areas' },
  { to: '/settings', label: 'Settings' },
  { to: '/sync', label: 'Sources' },
];

function useDarkMode() {
  const [dark, setDark] = useState(() => {
    try {
      return localStorage.getItem('theme') !== 'light';
    } catch {
      return true;
    }
  });
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
    try {
      localStorage.setItem('theme', dark ? 'dark' : 'light');
    } catch {
      // storage unavailable; theme still applies for this session
    }
  }, [dark]);
  return [dark, setDark] as const;
}

export default function App() {
  const [dark, setDark] = useDarkMode();
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-50 transition-colors dark:bg-gray-900">
        <nav className="border-b border-gray-200 bg-white px-4 py-2 dark:border-gray-700 dark:bg-gray-800">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-2">
            <span className="mr-2 text-sm font-semibold text-gray-900 dark:text-gray-100">🏠 Property Analyzer</span>
            <div className="flex gap-1 overflow-x-auto">
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) =>
                    `whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium ${
                      isActive
                        ? 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300'
                        : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-300 dark:hover:bg-gray-700 dark:hover:text-gray-100'
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </div>
            <div className="ml-auto flex items-center gap-2">
              <SyncBar />
              <button
                onClick={() => setDark(!dark)}
                className="rounded-md px-2 py-1 text-lg text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700"
                aria-label="Toggle dark mode"
              >
                {dark ? '☀️' : '🌙'}
              </button>
            </div>
          </div>
        </nav>
        <main className="mx-auto max-w-7xl px-4 py-6">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/listings" element={<Listings />} />
            <Route path="/listing/:id" element={<ListingDetail />} />
            <Route path="/sales" element={<Sales />} />
            <Route path="/sale/:id" element={<PropertyDetail />} />
            <Route path="/parcel/:parcelId" element={<PropertyDetail />} />
            <Route path="/garages" element={<Garages />} />
            <Route path="/watchlist" element={<Watchlist />} />
            <Route path="/regions" element={<Regions />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/sync" element={<SyncStatus />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
