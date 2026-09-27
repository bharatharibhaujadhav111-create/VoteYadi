-- Accuracy-first OCR queue for GitHub Actions.
-- Run once in Supabase Dashboard -> SQL Editor before enabling the workflow.

alter table public.documents drop constraint if exists documents_status_valid;
alter table public.documents add constraint documents_status_valid check (
  status in ('uploaded', 'queued', 'processing', 'ready', 'failed', 'needs_review', 'deleting')
);

alter table public.documents add column if not exists quality_report jsonb;

create or replace function public.claim_document_for_indexing(
  document_uuid uuid,
  worker_name text
)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  claimed integer;
begin
  update public.documents
     set status = 'processing',
         processing_started_at = now(),
         error_message = null,
         updated_at = now()
   where id = document_uuid
     and village_id is not null
     and (
       status in ('uploaded', 'queued')
       or (status = 'processing' and processing_started_at < now() - interval '6 hours')
     );
  get diagnostics claimed = row_count;
  if claimed = 0 then return false; end if;

  insert into public.processing_jobs(document_id, status, attempt, cloud_run_execution, started_at)
  values (
    document_uuid,
    'running',
    coalesce((select max(attempt) + 1 from public.processing_jobs where document_id = document_uuid), 1),
    left(coalesce(worker_name, 'github-actions'), 250),
    now()
  );
  return true;
end;
$$;

create or replace function public.publish_document_index(
  document_uuid uuid,
  worker_name text,
  voter_rows jsonb,
  parsed_pages integer,
  parsed_ocr_pages integer,
  report jsonb
)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  inserted integer;
begin
  if jsonb_typeof(voter_rows) <> 'array' or jsonb_array_length(voter_rows) = 0 then
    raise exception 'Cannot publish an empty voter index';
  end if;

  -- The old searchable version remains intact until this transaction commits.
  delete from public.voters where document_id = document_uuid;
  insert into public.voters (
    document_id, village_id, record_index, name, name_normalized, name_latin,
    relation_name, relation_name_normalized, relation_type, epic, serial, house,
    age, gender, part, section, page, script
  )
  select
    document_uuid, d.village_id, r.record_index, r.name, r.name_normalized,
    r.name_latin, r.relation_name, r.relation_name_normalized, r.relation_type,
    r.epic, r.serial, r.house, r.age, r.gender, r.part, r.section, r.page, r.script
  from public.documents d
  cross join jsonb_to_recordset(voter_rows) as r(
    record_index integer, name text, name_normalized text, name_latin text,
    relation_name text, relation_name_normalized text, relation_type text,
    epic text, serial text, house text, age integer, gender text, part text,
    section text, page integer, script text
  )
  where d.id = document_uuid and d.status = 'processing';
  get diagnostics inserted = row_count;
  if inserted <> jsonb_array_length(voter_rows) then
    raise exception 'Atomic publish rejected: expected % rows, inserted %', jsonb_array_length(voter_rows), inserted;
  end if;

  update public.documents
     set status = 'ready', active = true, page_count = parsed_pages,
         record_count = inserted, ocr_page_count = parsed_ocr_pages,
         indexed_at = now(), quality_report = report, error_message = null,
         updated_at = now()
   where id = document_uuid and status = 'processing';

  update public.processing_jobs
     set status = 'succeeded', progress = 100, pages_processed = parsed_pages,
         total_pages = parsed_pages, finished_at = now(), updated_at = now()
   where id = (
     select id from public.processing_jobs
      where document_id = document_uuid and status = 'running'
        and cloud_run_execution = left(coalesce(worker_name, 'github-actions'), 250)
      order by created_at desc limit 1
   );
  return inserted;
end;
$$;

create or replace function public.reject_document_index(
  document_uuid uuid,
  worker_name text,
  new_status text,
  failure_message text,
  report jsonb default '{}'::jsonb
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if new_status not in ('failed', 'needs_review', 'queued') then
    raise exception 'Invalid rejection status';
  end if;
  update public.documents
     set status = new_status, error_message = left(failure_message, 1000),
         quality_report = report, updated_at = now()
   where id = document_uuid and status = 'processing';
  update public.processing_jobs
     set status = 'failed', error_message = left(failure_message, 1000),
         finished_at = now(), updated_at = now()
   where id = (
     select id from public.processing_jobs
      where document_id = document_uuid and status = 'running'
        and cloud_run_execution = left(coalesce(worker_name, 'github-actions'), 250)
      order by created_at desc limit 1
   );
end;
$$;

revoke all on function public.claim_document_for_indexing(uuid,text) from public, anon, authenticated;
revoke all on function public.publish_document_index(uuid,text,jsonb,integer,integer,jsonb) from public, anon, authenticated;
revoke all on function public.reject_document_index(uuid,text,text,text,jsonb) from public, anon, authenticated;
grant execute on function public.claim_document_for_indexing(uuid,text) to service_role;
grant execute on function public.publish_document_index(uuid,text,jsonb,integer,integer,jsonb) to service_role;
grant execute on function public.reject_document_index(uuid,text,text,text,jsonb) to service_role;
