-- Super Admin review list. This never merges, hides, or changes voter rows.
create or replace function public.admin_duplicate_voters()
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
  ),
  epic_groups as (
    select upper(epic) as match_key, min(epic) as label, count(*) as count,
           jsonb_agg(jsonb_build_object(
             'id', id, 'name', name, 'relation_name', relation_name,
             'epic', epic, 'serial', serial, 'page', page,
             'village', village, 'pdf', document_id,
             'pdf_name', pdf_name
           ) order by village, pdf_name, page, id) as records
      from active
     where btrim(epic) <> ''
     group by upper(epic)
    having count(*) > 1
  ),
  name_groups as (
    select village_id::text || ':' || name_normalized || ':' || relation_name_normalized as match_key,
           min(name) as label, min(relation_name) as relation_label,
           count(*) as count,
           jsonb_agg(jsonb_build_object(
             'id', id, 'name', name, 'relation_name', relation_name,
             'epic', epic, 'serial', serial, 'page', page,
             'village', village, 'pdf', document_id,
             'pdf_name', pdf_name
           ) order by pdf_name, page, id) as records
      from active
     where btrim(name_normalized) <> '' and btrim(relation_name_normalized) <> ''
     group by village_id, name_normalized, relation_name_normalized
    having count(*) > 1
  )
  select jsonb_build_object(
    'epic', coalesce((select jsonb_agg(jsonb_build_object(
      'key', match_key, 'label', label, 'count', count, 'records', records
    ) order by label) from epic_groups), '[]'::jsonb),
    'name', coalesce((select jsonb_agg(jsonb_build_object(
      'key', match_key, 'label', label, 'relation_label', relation_label,
      'count', count, 'records', records
    ) order by label) from name_groups), '[]'::jsonb)
  );
$$;

revoke all on function public.admin_duplicate_voters() from public, anon, authenticated;
grant execute on function public.admin_duplicate_voters() to service_role;

create index if not exists voters_duplicate_name_idx
  on public.voters (village_id, name_normalized, relation_name_normalized)
  where name_normalized <> '' and relation_name_normalized <> '';
