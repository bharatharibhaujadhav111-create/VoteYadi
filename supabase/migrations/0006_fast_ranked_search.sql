-- One-pass, field-aware voter search.
-- Run once in Supabase Dashboard -> SQL Editor before deploying the Worker.

alter table public.voters
  add column if not exists relation_name_latin text not null default '';

-- Most relatives also occur as voters in the same roll. Reuse their already
-- generated Latin form so existing PDFs gain English relative-name search
-- without OCR or re-indexing.
create index if not exists voters_name_normalized_btree_idx
  on public.voters (name_normalized);

update public.voters target
set relation_name_latin = (
  select candidate.name_latin
  from public.voters candidate
  where candidate.name_normalized = target.relation_name_normalized
    and candidate.name_latin <> ''
  order by (candidate.village_id = target.village_id) desc, candidate.id
  limit 1
)
where target.relation_name_latin = ''
  and target.relation_name_normalized <> ''
  and exists (
    select 1 from public.voters candidate
    where candidate.name_normalized = target.relation_name_normalized
      and candidate.name_latin <> ''
  );

create index if not exists voters_relation_latin_trgm_idx
  on public.voters using gin (relation_name_latin extensions.gin_trgm_ops);

create or replace function public.search_voters_ranked(
  search_text text,
  village_name text default '',
  page_number integer default 1,
  page_size integer default 20
)
returns jsonb
language sql
stable
security definer
set search_path = public, extensions
as $$
with input as (
  select
    lower(regexp_replace(btrim(coalesce(search_text, '')), '\s+', ' ', 'g')) as q,
    split_part(lower(regexp_replace(btrim(coalesce(search_text, '')), '\s+', ' ', 'g')), ' ', 1) as first_token,
    greatest(page_number, 1) as requested_page,
    least(greatest(page_size, 1), 100) as requested_size,
    coalesce(search_text, '') ~ '[A-Za-z]' and coalesce(search_text, '') !~ '[ऀ-ॿ]' as roman
), base as (
  select v.id, v.name, v.relation_name, v.relation_type, v.epic, v.serial,
         v.part, v.house, v.age, v.gender, v.page, d.id as document_id,
         d.original_filename, g.name as village,
         case when i.roman then v.name_latin else v.name_normalized end as own_value,
         case when i.roman then v.relation_name_latin else v.relation_name_normalized end as relation_value,
         i.q, i.first_token, i.requested_page, i.requested_size
  from public.voters v
  join public.documents d on d.id = v.document_id and d.status = 'ready' and d.active
  join public.villages g on g.id = v.village_id and g.active
  cross join input i
  where i.q <> ''
    and (village_name = '' or lower(g.name) = lower(village_name))
), matched as (
  select b.*,
    upper(b.epic) = upper(b.q) as epic_match,
    not exists (
      select 1 from regexp_split_to_table(b.q, '\s+') token
      where b.own_value not ilike '%' || token || '%'
    ) as own_tokens,
    not exists (
      select 1 from regexp_split_to_table(b.q, '\s+') token
      where b.relation_value not ilike '%' || token || '%'
    ) as relation_tokens,
    similarity(b.own_value, b.q) as own_similarity,
    similarity(b.relation_value, b.q) as relation_similarity
  from base b
  where b.own_value ilike '%' || b.q || '%'
     or b.relation_value ilike '%' || b.q || '%'
     or b.own_value % b.q
     or b.relation_value % b.q
     or upper(b.epic) = upper(b.q)
), scored as (
  select m.*,
    case
      when epic_match then 1000
      when own_tokens and own_value = q then 106
      -- Latin transliteration commonly adds a trailing vowel (bharat ->
      -- bharata). Prefix matching the first requested token therefore gives
      -- the intended first-name priority without requiring literal equality.
      when own_tokens and own_value like first_token || '%' then 105
      when own_tokens and (' ' || own_value || ' ') like '% ' || q || ' %' then 104
      when own_tokens then 103
      when own_similarity >= 0.24 then 101
      when relation_tokens and relation_value = q then 6
      when relation_tokens and relation_value like first_token || '%' then 5
      when relation_tokens and (' ' || relation_value || ' ') like '% ' || q || ' %' then 4
      when relation_tokens then 3
      when relation_similarity >= 0.24 then 1
      else 0
    end as field_rank,
    case when own_tokens or own_similarity >= 0.24
      then own_similarity else relation_similarity end as relevance
  from matched m
), accepted as (
  select * from scored where field_rank > 0
), totals as (
  select count(*)::bigint as total from accepted
), page_rows as (
  select * from accepted
  order by field_rank desc, relevance desc, name, id
  limit (select requested_size from input)
  offset ((select requested_page - 1 from input) * (select requested_size from input))
), payload as (
  select coalesce(jsonb_agg(jsonb_build_object(
    'id', id, 'name', name, 'relation_name', relation_name,
    'relation_type', relation_type, 'epic', epic, 'serial', serial,
    'part', part, 'house', house, 'age', coalesce(age::text, ''),
    'gender', gender, 'page', page, 'pdf', document_id::text,
    'pdf_name', original_filename, 'village', village,
    'score', round((relevance * 100)::numeric, 1)
  ) order by field_rank desc, relevance desc, name, id), '[]'::jsonb) as rows
  from page_rows
)
select jsonb_build_object(
  'results', payload.rows,
  'total', totals.total,
  'page', input.requested_page,
  'page_size', input.requested_size,
  'query', jsonb_build_object('text', search_text),
  'relaxed', false,
  'suggestions', '[]'::jsonb
)
from input cross join totals cross join payload;
$$;

revoke all on function public.search_voters_ranked(text,text,integer,integer)
  from public, anon, authenticated;
grant execute on function public.search_voters_ranked(text,text,integer,integer)
  to service_role;

notify pgrst, 'reload schema';
