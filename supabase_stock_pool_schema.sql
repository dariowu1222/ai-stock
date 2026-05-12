-- Supabase schema for AI?? ?????????.
-- MCP ????????? Supabase SQL editor ? migration ????

create table if not exists public.ai_tw_stock_pool (
  stock_id text primary key,
  stock_name text not null default '',
  market text not null default '',
  industry_category text not null default '',
  rank integer,
  strength_score numeric(10,4),
  is_tech_focus boolean not null default false,
  popularity_weight numeric(8,4) not null default 1,
  theme_tags text,
  latest_date date,
  latest_close numeric(18,4),
  latest_volume bigint,
  avg_volume_20 numeric(20,2),
  ma5 numeric(18,4),
  ma20 numeric(18,4),
  ma60 numeric(18,4),
  return_5d numeric(12,6),
  return_20d numeric(12,6),
  return_60d numeric(12,6),
  volume_ratio_20 numeric(12,6),
  rsi14 numeric(10,4),
  volatility_20 numeric(12,6),
  high_20 numeric(18,4),
  high_60 numeric(18,4),
  distance_from_60d_high numeric(12,6),
  trend_flags integer,
  source_file text,
  generated_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_ai_tw_stock_pool_rank
  on public.ai_tw_stock_pool (rank);

create index if not exists idx_ai_tw_stock_pool_strength_score
  on public.ai_tw_stock_pool (strength_score desc);

create index if not exists idx_ai_tw_stock_pool_tech_hot
  on public.ai_tw_stock_pool (is_tech_focus, popularity_weight desc, strength_score desc);

create index if not exists idx_ai_tw_stock_pool_market_industry
  on public.ai_tw_stock_pool (market, industry_category);

create table if not exists public.ai_tw_stock_daily_price (
  stock_id text not null references public.ai_tw_stock_pool(stock_id) on delete cascade,
  trade_date date not null,
  open numeric(18,4) not null,
  high numeric(18,4) not null,
  low numeric(18,4) not null,
  close numeric(18,4) not null,
  volume bigint not null,
  created_at timestamptz not null default now(),
  primary key (stock_id, trade_date)
);

create index if not exists idx_ai_tw_stock_daily_price_trade_date
  on public.ai_tw_stock_daily_price (trade_date desc);
