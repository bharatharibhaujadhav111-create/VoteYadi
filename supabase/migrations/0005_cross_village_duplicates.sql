-- Cross-village review only: never changes, merges, or hides voter rows.
-- The function reads current ready documents, so new indexing is included automatically.
create or replace function public.admin_cross_village_duplicates()
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
  with active as materialized (
    select v.id, v.name, v.name_normalized, v.relation_name,
           v.relation_name_normalized, v.epic, v.serial, v.page,
           v.village_id, g.name as village, d.id as document_id,
           d.original_filename as pdf_name
      from public.voters v
      join public.documents d on d.id = v.document_id
        and d.status = 'ready' and d.active
      join public.villages g on g.id = v.village_id and g.active
     where btrim(v.name_normalized) <> ''
       and btrim(v.relation_name_normalized) <> ''
  ),
  same_relative as (
    select name_normalized || ':' || relation_name_normalized as match_key,
           min(name) as label, min(relation_name) as relation_label,
           count(*) as match_count,
           jsonb_agg(jsonb_build_object(
             'id', id, 'name', name, 'relation_name', relation_name,
             'epic', epic, 'serial', serial, 'page', page,
             'village', village, 'pdf', document_id,
             'pdf_name', pdf_name
           ) order by village, pdf_name, page, id) as records
      from active
     group by name_normalized, relation_name_normalized
    having count(distinct village_id) > 1
  ),
  different_relative as (
    select name_normalized as match_key, min(name) as label,
           count(*) as match_count,
           jsonb_agg(jsonb_build_object(
             'id', id, 'name', name, 'relation_name', relation_name,
             'epic', epic, 'serial', serial, 'page', page,
             'village', village, 'pdf', document_id,
             'pdf_name', pdf_name
           ) order by village, relation_name, pdf_name, page, id) as records
      from active
     group by name_normalized
    having count(distinct village_id) > 1
       and count(distinct relation_name_normalized) > 1
  )
  select jsonb_build_object(
    'same_relative', coalesce((select jsonb_agg(jsonb_build_object(
      'key', match_key, 'label', label, 'relation_label', relation_label,
      'count', match_count, 'records', records
    ) order by label) from same_relative), '[]'::jsonb),
    'different_relative', coalesce((select jsonb_agg(jsonb_build_object(
      'key', match_key, 'label', label, 'relation_label', '',
      'count', match_count, 'records', records
    ) order by label) from different_relative), '[]'::jsonb)
  );
$$;

revoke all on function public.admin_cross_village_duplicates() from public, anon, authenticated;
grant execute on function public.admin_cross_village_duplicates() to service_role;

create index if not exists voters_cross_village_duplicate_idx
  on public.voters (name_normalized, relation_name_normalized, village_id)
  where name_normalized <> '' and relation_name_normalized <> '';
