# GitHub OCR setup

The workflow processes one pending PDF per job and runs at most four PDF jobs
at once. It runs automatically every 15 minutes and can also be started from
GitHub **Actions → Index pending voter PDFs → Run workflow**.

## One-time setup

1. In Supabase SQL Editor, run `supabase/migrations/0003_github_ocr_queue.sql`.
2. In GitHub open **Repository → Settings → Secrets and variables → Actions**.
3. Add these repository secrets:
   - `SUPABASE_URL`
   - `SUPABASE_SECRET_KEY`
   - `R2_ENDPOINT_URL`
   - `R2_ACCESS_KEY_ID`
   - `R2_SECRET_ACCESS_KEY`
   - `R2_BUCKET` (normally `voteyadi-pdfs`)
4. Push the workflow and code to the repository's `main` branch.
5. Open the Actions tab and manually run the workflow once.

Use a dedicated R2 API token restricted to the VoteYadi PDF bucket. Never put
secret values in this file, workflow logs, commits, or screenshots.

## Processing rules

- One PDF is exclusively claimed by one job.
- Infrastructure failures retry up to two times.
- Suspicious OCR is marked `needs_review` and is not published.
- Each PDF job runs parser tests, then checks that the PDF has enough Marathi
  names, at least 95% serial coverage, no serial collisions, and a complete
  serial sequence for rolls starting at 1. Suspect pages get a bilingual
  numeric re-read; Marathi-only names are retained.
- Repeated names or EPIC numbers are kept as separate searchable records and
  recorded as quality warnings, not reasons to reject the PDF.
- A job that cannot claim a PDF reports `skipped` and fails visibly; rerunning
  an old job is not the way to retry `needs_review` documents.
- Valid rows replace the previous PDF index in a single database transaction.
- Existing searchable rows survive runner crashes and failed replacement runs.

## Super Admin duplicate review

Run `supabase/migrations/0004_admin_duplicates.sql` once in the Supabase SQL
Editor before using the **Duplicates** tab. It groups active searchable records
by exact EPIC and by full name plus relative's name within the same village.
It does not merge or delete voter records.
