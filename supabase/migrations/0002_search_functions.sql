-- Database-side search used by the Cloudflare Worker.
-- The Worker holds the service-role key; these functions are not directly
-- exposed to browser roles.

alter table public.documents alter column village_id drop not null;

create or replace function public.search_voters(
  search_text text,
  village_name text default '',
  page_number integer default 1,
  page_size integer default 20
)
returns jsonb
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  q text := lower(btrim(coalesce(search_text, '')));
  q_norm text := regexp_replace(lower(btrim(coalesce(search_text, ''))), '\s+', ' ', 'g');
  skip integer := greatest(0, (greatest(page_number, 1) - 1) * least(greatest(page_size, 1), 100));
  take integer := least(greatest(page_size, 1), 100);
  total_count bigint;
  rows jsonb;
begin
  if q = '' then
    return jsonb_build_object('results', '[]'::jsonb, 'total', 0, 'page', greatest(page_number,1), 'page_size', take, 'query', jsonb_build_object('text', search_text), 'relaxed', false, 'suggestions', '[]'::jsonb);
  end if;

  with matches as (
    select v.id, v.name, v.relation_name, v.relation_type, v.epic, v.serial,
           v.part, v.house, v.age, v.gender, v.page, d.id as document_id,
           d.original_filename, g.name as village,
           greatest(
             similarity(v.name_normalized, q_norm),
             similarity(lower(v.name), q),
             similarity(v.name_latin, q_norm),
             similarity(v.relation_name_normalized, q_norm),
             case when upper(v.epic) = upper(q) then 1.0 else 0.0 end
           ) as score
    from public.voters v
    join public.documents d on d.id = v.document_id and d.status = 'ready' and d.active
    join public.villages g on g.id = v.village_id and g.active
    where (village_name = '' or lower(g.name) = lower(village_name))
      and (
        lower(v.name) like '%' || q || '%'
        or v.name_normalized like '%' || q_norm || '%'
        or v.name_latin like '%' || q_norm || '%'
        or v.relation_name_normalized like '%' || q_norm || '%'
        or upper(v.epic) = upper(q)
        or similarity(v.name_normalized, q_norm) >= 0.24
        or similarity(v.name_latin, q_norm) >= 0.24
      )
  )
  select count(*) into total_count from matches;

  with matches as (
    select v.id, v.name, v.relation_name, v.relation_type, v.epic, v.serial,
           v.part, v.house, v.age, v.gender, v.page, d.id as document_id,
           d.original_filename, g.name as village,
           greatest(similarity(v.name_normalized, q_norm), similarity(lower(v.name), q), similarity(v.name_latin, q_norm), similarity(v.relation_name_normalized, q_norm), case when upper(v.epic) = upper(q) then 1.0 else 0.0 end) as score
    from public.voters v
    join public.documents d on d.id = v.document_id and d.status = 'ready' and d.active
    join public.villages g on g.id = v.village_id and g.active
    where (village_name = '' or lower(g.name) = lower(village_name))
      and (lower(v.name) like '%' || q || '%' or v.name_normalized like '%' || q_norm || '%' or v.name_latin like '%' || q_norm || '%' or v.relation_name_normalized like '%' || q_norm || '%' or upper(v.epic) = upper(q) or similarity(v.name_normalized, q_norm) >= 0.24 or similarity(v.name_latin, q_norm) >= 0.24)
  )
  select coalesce(jsonb_agg(jsonb_build_object(
    'id', id, 'name', name, 'relation_name', relation_name, 'relation_type', relation_type,
    'epic', epic, 'serial', serial, 'part', part, 'house', house,
    'age', coalesce(age::text, ''), 'gender', gender, 'page', page,
    'pdf', document_id::text, 'pdf_name', original_filename, 'village', village,
    'score', round((score * 100)::numeric, 1)
  ) order by score desc, name), '[]'::jsonb) into rows
  from (select * from matches order by score desc, name limit take offset skip) ranked;

  return jsonb_build_object('results', rows, 'total', total_count, 'page', greatest(page_number,1), 'page_size', take, 'query', jsonb_build_object('text', search_text), 'relaxed', false, 'suggestions', '[]'::jsonb);
end;
$$;

create or replace function public.suggest_voters(search_text text, village_name text default '', result_limit integer default 8)
returns table(text text, name text, relation_name text, relation_type text, village text, pdf text, page integer, age text, gender text)
language sql
security definer
set search_path = public, extensions
as $$
  select v.name as text, v.name, v.relation_name, v.relation_type, g.name,
         d.id::text, v.page, coalesce(v.age::text, ''), v.gender
  from public.voters v
  join public.documents d on d.id = v.document_id and d.status = 'ready' and d.active
  join public.villages g on g.id = v.village_id and g.active
  where (village_name = '' or lower(g.name) = lower(village_name))
    and (lower(v.name) like '%' || lower(btrim(search_text)) || '%' or similarity(v.name_normalized, lower(btrim(search_text))) >= 0.24)
  order by similarity(v.name_normalized, lower(btrim(search_text))) desc, v.name
  limit least(greatest(result_limit, 1), 20)
$$;

revoke all on function public.search_voters(text,text,integer,integer) from public, anon, authenticated;
revoke all on function public.suggest_voters(text,text,integer) from public, anon, authenticated;
grant execute on function public.search_voters(text,text,integer,integer) to service_role;
grant execute on function public.suggest_voters(text,text,integer) to service_role;
