-- RentCast usage now lives in data/rentcast_ledger.jsonl (rolling 31-day window, survives db resets).
DROP TABLE IF EXISTS rentcast_usage;
