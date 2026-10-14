-- 席次表資料放在獨立的 `seating` schema，與 wedding 專案其他資料（例如 song）分開。
-- 這個 schema 不對外開放：anon 沒有任何表權限，只能透過 public 底下的三個函式存取。
--
--   public.seating_get(event)                       讀整份席次（公開，賓客也能讀）
--   public.seating_check_key(event, key)            工作人員網址的編輯金鑰是否正確
--   public.seating_save(event, key, tables jsonb)   寫入一桌或多桌（需要金鑰）
--
-- 編輯金鑰只存 sha256 雜湊；明碼只出現在工作人員網址 ?edit=<key>。

create schema if not exists seating;
revoke all on schema seating from public, anon, authenticated;

create table if not exists seating.events (
  id text primary key check (id ~ '^[a-z0-9-]{3,40}$'),
  edit_key_hash text not null check (edit_key_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null default now()
);

create table if not exists seating.tables (
  event_id text not null references seating.events (id) on delete cascade,
  table_id text not null check (table_id ~ '^(main|t[0-9]{1,2})$'),
  num text not null default '' check (char_length(num) <= 6),
  name text not null default '' check (char_length(name) <= 20),   -- 桌名，例如「大學同學」
  side text not null default '' check (side in ('', '主婚人親友', '新人親友')),
  cap int not null default 10 check (cap between 1 and 30),
  guests jsonb not null default '[]'::jsonb
    check (jsonb_typeof(guests) = 'array' and jsonb_array_length(guests) <= 40 and octet_length(guests::text) < 4000),
  updated_at timestamptz not null default now(),
  primary key (event_id, table_id)
);

-- 兒童座椅在桌邊的位置（角度，度；0＝右、90＝下），工作人員可拖曳調整；空陣列＝自動擺在離走道最遠處
alter table seating.tables add column if not exists kid_seats jsonb not null default '[]'::jsonb;
do $$ begin
  alter table seating.tables add constraint kid_seats_valid
    check (jsonb_typeof(kid_seats) = 'array' and jsonb_array_length(kid_seats) <= 10
           and not jsonb_path_exists(kid_seats, '$[*] ? (@.type() != "number" || @ < -360 || @ > 360)'));
exception when duplicate_object then null; end $$;

-- 已建立的資料表補上桌名欄位
alter table seating.tables add column if not exists name text not null default '' check (char_length(name) <= 20);

-- 賓客名單每一筆是一組人：{ "name": 代表人姓名, "count": 這組共幾位, "child": 兒童座椅數（選填） }
-- （舊版存成字串「王小明 +2」＝3 位，這裡一併轉成新格式）
alter table seating.tables drop constraint if exists guests_are_strings;
update seating.tables t set guests = coalesce((
  select jsonb_agg(case
    when jsonb_typeof(g) = 'string' then jsonb_build_object(
      'name', btrim(regexp_replace(g #>> '{}', '\s*[+＋]\s*\d+$', '')),
      'count', 1 + coalesce((regexp_match(g #>> '{}', '[+＋]\s*(\d+)$'))[1]::int, 0))
    else g end)
  from jsonb_array_elements(t.guests) g), '[]'::jsonb)
where exists (select 1 from jsonb_array_elements(t.guests) g where jsonb_typeof(g) = 'string');
-- child（選填）＝這組需要幾張兒童座椅
alter table seating.tables drop constraint if exists guests_are_parties;
alter table seating.tables add constraint guests_are_parties
  check (not jsonb_path_exists(guests,
    '$[*] ? (@.type() != "object" || !exists(@.name) || !exists(@.count) || @.name.type() != "string" || @.count.type() != "number" || @.count < 1 || @.count > 20 || (exists(@.child) && (@.child.type() != "number" || @.child < 0 || @.child > 10)))'));

alter table seating.events enable row level security;
alter table seating.tables enable row level security;

-- 讀：{ "tables": { "<table_id>": { num, name, side, cap, guests, updated_at } }, "updated_at": 最新修改時間 }
create or replace function public.seating_get(p_event text)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'tables', coalesce(jsonb_object_agg(t.table_id, jsonb_build_object(
      'num', t.num, 'name', t.name, 'side', t.side, 'cap', t.cap, 'guests', t.guests, 'kidAngles', t.kid_seats, 'updated_at', t.updated_at)), '{}'::jsonb),
    'updated_at', max(t.updated_at)
  )
  from seating.tables t
  where t.event_id = p_event;
$$;

create or replace function public.seating_check_key(p_event text, p_key text)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from seating.events e
    where e.id = p_event
      and e.edit_key_hash = encode(pg_catalog.sha256(convert_to(coalesce(p_key, ''), 'UTF8')), 'hex')
  );
$$;

-- 寫：p_tables = { "<table_id>": { num, name, side, cap, guests, kidAngles } }，只覆蓋有傳的桌；回傳寫入時間
create or replace function public.seating_save(p_event text, p_key text, p_tables jsonb)
returns timestamptz
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_now timestamptz := now();
begin
  if not public.seating_check_key(p_event, p_key) then
    raise exception 'invalid edit key' using errcode = '42501';
  end if;
  if jsonb_typeof(p_tables) <> 'object' or (select count(*) from jsonb_object_keys(p_tables)) > 60 then
    raise exception 'invalid payload' using errcode = '22023';
  end if;

  insert into seating.tables as t (event_id, table_id, num, name, side, cap, guests, kid_seats, updated_at)
  select p_event, k,
         coalesce(v ->> 'num', ''),
         coalesce(v ->> 'name', ''),
         coalesce(v ->> 'side', ''),
         coalesce((v ->> 'cap')::int, 10),
         coalesce(v -> 'guests', '[]'::jsonb),
         coalesce(v -> 'kidAngles', '[]'::jsonb),
         v_now
  from jsonb_each(p_tables) as x(k, v)
  on conflict (event_id, table_id) do update
    set num = excluded.num, name = excluded.name, side = excluded.side, cap = excluded.cap,
        guests = excluded.guests, kid_seats = excluded.kid_seats, updated_at = excluded.updated_at;

  return v_now;
end;
$$;

revoke all on function public.seating_get(text) from public;
revoke all on function public.seating_check_key(text, text) from public;
revoke all on function public.seating_save(text, text, jsonb) from public;
grant execute on function public.seating_get(text) to anon, authenticated;
grant execute on function public.seating_check_key(text, text) to anon, authenticated;
grant execute on function public.seating_save(text, text, jsonb) to anon, authenticated;

-- ───────────── 出席名單（工作人員專用，需要編輯金鑰才能讀寫）─────────────
-- 由 tools/import_roster.py 從出席調查試算表匯入；只存排座位需要的欄位，不存電話與留言。
-- people = [{ "name", "count", "side", "relation", "unit", "veg", "child", "note" }, …]
create table if not exists seating.rosters (
  event_id text primary key references seating.events (id) on delete cascade,
  people jsonb not null default '[]'::jsonb
    check (jsonb_typeof(people) = 'array' and jsonb_array_length(people) <= 600 and octet_length(people::text) < 200000),
  updated_at timestamptz not null default now()
);
alter table seating.rosters enable row level security;

create or replace function public.seating_get_roster(p_event text, p_key text)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  if not public.seating_check_key(p_event, p_key) then
    raise exception 'invalid edit key' using errcode = '42501';
  end if;
  return coalesce((select jsonb_build_object('people', r.people, 'updated_at', r.updated_at)
                   from seating.rosters r where r.event_id = p_event),
                  jsonb_build_object('people', '[]'::jsonb, 'updated_at', null));
end;
$$;

create or replace function public.seating_set_roster(p_event text, p_key text, p_people jsonb)
returns timestamptz
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_now timestamptz := now();
begin
  if not public.seating_check_key(p_event, p_key) then
    raise exception 'invalid edit key' using errcode = '42501';
  end if;
  insert into seating.rosters (event_id, people, updated_at) values (p_event, p_people, v_now)
  on conflict (event_id) do update set people = excluded.people, updated_at = excluded.updated_at;
  return v_now;
end;
$$;

revoke all on function public.seating_get_roster(text, text) from public;
revoke all on function public.seating_set_roster(text, text, jsonb) from public;
grant execute on function public.seating_get_roster(text, text) to anon, authenticated;
grant execute on function public.seating_set_roster(text, text, jsonb) to anon, authenticated;
