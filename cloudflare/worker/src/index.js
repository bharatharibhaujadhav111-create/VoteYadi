const json = (data, status = 200, extra = {}) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", ...extra },
  });

function cors(env) {
  return {
    "access-control-allow-origin": env.ALLOWED_ORIGIN || "*",
    "access-control-allow-methods": "GET,POST,DELETE,OPTIONS",
    "access-control-allow-headers": "content-type, range, if-range",
    "access-control-expose-headers": "accept-ranges, content-length, content-range, etag",
  };
}

function safeName(value) {
  return String(value || "upload.pdf")
    .replace(/[\\/]/g, "_")
    .replace(/[^\p{L}\p{N}._ -]/gu, "_")
    .slice(0, 180);
}

function slug(value) {
  return String(value || "unassigned")
    .normalize("NFKC")
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "") || "unassigned";
}

const DEVANAGARI_CONSONANTS = {
  "क": "k", "ख": "k", "ग": "g", "घ": "g", "ङ": "n",
  "च": "c", "छ": "c", "ज": "j", "झ": "j", "ञ": "n",
  "ट": "t", "ठ": "t", "ड": "d", "ढ": "d", "ण": "n",
  "त": "t", "थ": "t", "द": "d", "ध": "d", "न": "n",
  "प": "p", "फ": "p", "ब": "b", "भ": "b", "म": "m",
  "य": "y", "र": "r", "ल": "l", "ळ": "l", "व": "v",
  "श": "s", "ष": "s", "स": "s", "ह": "h", "ं": "n",
};

function isRomanName(value) {
  const text = String(value || "").trim();
  return /[a-z]/i.test(text) && !/[\u0900-\u097f]/.test(text);
}

// A vowel-insensitive Marathi name key. It intentionally merges aspirated
// consonants (dh/d, bh/b, etc.), because informal English spellings vary.
function phoneticKey(value) {
  const text = String(value || "").toLowerCase().normalize("NFKC");
  if (/[\u0900-\u097f]/.test(text)) {
    return [...text].map(ch => DEVANAGARI_CONSONANTS[ch] || "").join("")
      .replace(/(.)\1+/g, "$1");
  }
  return text
    .replace(/sh|ss/g, "s").replace(/ch/g, "c")
    .replace(/kh/g, "k").replace(/gh/g, "g").replace(/jh/g, "j")
    .replace(/th/g, "t").replace(/dh/g, "d").replace(/ph|f/g, "p")
    .replace(/bh/g, "b").replace(/w/g, "v").replace(/z/g, "j")
    .replace(/[aeiouy\W_]/g, "").replace(/(.)\1+/g, "$1");
}

function editDistance(a, b) {
  const row = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    let diagonal = row[0];
    row[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const above = row[j];
      row[j] = Math.min(row[j] + 1, row[j - 1] + 1, diagonal + (a[i - 1] === b[j - 1] ? 0 : 1));
      diagonal = above;
    }
  }
  return row[b.length];
}

function tokenSimilarity(a, b) {
  if (!a || !b) return 0;
  if (a === b) return 1;
  return 1 - editDistance(a, b) / Math.max(a.length, b.length);
}

function englishNameMatch(query, marathiName) {
  const queryTokens = query.trim().split(/\s+/).map(phoneticKey).filter(Boolean);
  const nameWords = String(marathiName || "").trim().split(/\s+/);
  const nameTokens = nameWords.map(phoneticKey);
  if (!queryTokens.length || !nameTokens.length) return { score: 0, tier: 0, marathi: "" };
  const chosen = [];
  const used = new Set();
  const matches = queryTokens.map(q => {
    let best = { score: 0, index: -1 };
    nameTokens.forEach((n, index) => {
      if (used.has(index)) return;
      const score = tokenSimilarity(q, n);
      if (score > best.score) best = { score, index };
    });
    if (best.index >= 0) used.add(best.index);
    if (best.index >= 0 && best.score >= 0.45) chosen.push(nameWords[best.index]);
    return best;
  });
  const scores = matches.map(match => match.score);
  const coverage = scores.reduce((sum, score) => sum + score, 0) / queryTokens.length;
  const exact = scores.filter(score => score >= 0.99).length / queryTokens.length;
  const positions = matches.map(match => match.index);
  const allExact = exact === 1;
  const ordered = positions.every((position, index) => index === 0 || position > positions[index - 1]);
  const consecutive = ordered && positions.every(
    (position, index) => index === 0 || position === positions[index - 1] + 1,
  );
  const startsName = consecutive && positions[0] === 0;
  const firstTokenExact = tokenSimilarity(queryTokens[0], nameTokens[0]) >= 0.99;
  let tier = 0;
  if (allExact && startsName) tier = 6;
  else if (allExact && firstTokenExact) tier = 5;
  else if (allExact && consecutive) tier = 4;
  else if (allExact) tier = 3;
  else if (coverage >= 0.72 && firstTokenExact) tier = 2;
  else if (coverage >= 0.58) tier = 1;
  return {
    score: coverage * 80 + exact * 20,
    tier,
    marathi: [...new Set(chosen)].join(" "),
  };
}

function rerankEnglish(body, query, page, pageSize) {
  const ranked = (body?.results || []).map(item => {
    const match = englishNameMatch(query, item.name);
    return { ...item, score: Math.round(match.score * 10) / 10, _tier: match.tier, _marathi: match.marathi };
  }).filter(item => item._tier > 0)
    .sort((a, b) => b._tier - a._tier || b.score - a.score
      || String(a.name).localeCompare(String(b.name), "mr"));
  const start = (page - 1) * pageSize;
  const interpreted = ranked[0]?._marathi || ranked[0]?.name || "";
  return {
    ...body,
    results: ranked.slice(start, start + pageSize).map(({ _marathi, _tier, ...item }) => item),
    total: ranked.length,
    page,
    page_size: pageSize,
    query: { ...(body?.query || {}), text: query, original: query, transliterated: interpreted, script: "latin" },
  };
}

async function englishCandidates(env, searchText, villageName) {
  const batchSize = 100;
  const firstArgs = { search_text: searchText, village_name: villageName, page_number: 1, page_size: batchSize };
  const { body: first } = await db(env, "rpc/search_voters", {
    method: "POST", body: JSON.stringify(firstArgs),
  });
  const total = Math.max(0, Number(first?.total || 0));
  // A village normally has far fewer candidates. This ceiling keeps unusually
  // broad all-village queries within Cloudflare's subrequest allowance.
  const pages = Math.min(20, Math.ceil(total / batchSize));
  const results = [...(first?.results || [])];
  for (let start = 2; start <= pages; start += 5) {
    const requests = [];
    for (let page = start; page < Math.min(start + 5, pages + 1); page += 1) {
      requests.push(db(env, "rpc/search_voters", {
        method: "POST",
        body: JSON.stringify({ ...firstArgs, page_number: page }),
      }));
    }
    const batches = await Promise.all(requests);
    batches.forEach(batch => results.push(...(batch.body?.results || [])));
  }
  return { ...(first || {}), results, candidate_total: total, candidate_limit_reached: total > 2000 };
}

async function db(env, path, init = {}) {
  const apiKey = env.SUPABASE_SECRET_KEY || env.SUPABASE_SERVICE_ROLE_KEY;
  if (!apiKey) throw new Error("Supabase secret is not configured");
  const authHeaders = apiKey.startsWith("sb_secret_")
    ? {}
    : { authorization: `Bearer ${apiKey}` };
  const response = await fetch(`${env.SUPABASE_URL}/rest/v1/${path}`, {
    ...init,
    headers: {
      apikey: apiKey,
      ...authHeaders,
      "content-type": "application/json",
      prefer: "return=representation",
      ...(init.headers || {}),
    },
  });
  const text = await response.text();
  let body = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = text; }
  if (!response.ok) throw new Error(body?.message || body?.hint || text || `Database error ${response.status}`);
  return { body, headers: response.headers };
}

async function villageByName(env, name) {
  const q = encodeURIComponent(name);
  const { body } = await db(env, `villages?select=id,name&name=eq.${q}&limit=1`);
  return body?.[0] || null;
}

async function ensureVillage(env, name) {
  const clean = String(name || "").trim();
  if (!clean) return null;
  const existing = await villageByName(env, clean);
  if (existing) return existing;
  try {
    const { body } = await db(env, "villages", {
      method: "POST",
      body: JSON.stringify({ name: clean, slug: slug(clean) }),
    });
    return body[0];
  } catch (error) {
    // A simultaneous upload may have created the same village first.
    const raced = await villageByName(env, clean);
    if (raced) return raced;
    throw error;
  }
}

async function listVillages(env) {
  const { body } = await db(env, "villages?select=id,name,active,documents(id,status,record_count)&order=name.asc");
  return (body || []).filter(v => v.active).map(v => ({
    id: v.id,
    name: v.name,
    pdfs: (v.documents || []).length,
    records: (v.documents || []).filter(d => d.status === "ready").reduce((n, d) => n + (d.record_count || 0), 0),
  }));
}

function pdfJson(d) {
  return {
    id: d.id,
    name: d.original_filename,
    village: d.villages?.name || "",
    size: d.size_bytes || 0,
    pages: d.page_count || 0,
    uploaded_at: d.uploaded_at || "",
    indexed: d.status === "ready",
    records: d.record_count || 0,
    ocr_pages: d.ocr_page_count || 0,
    status: d.status,
    error: d.error_message,
  };
}

async function documents(env, params) {
  let path = "documents?select=id,original_filename,r2_key,size_bytes,page_count,status,error_message,record_count,ocr_page_count,uploaded_at,village_id,villages(name)&order=uploaded_at.desc";
  if (params.get("q")) path += `&original_filename=ilike.*${encodeURIComponent(params.get("q"))}*`;
  if (params.has("village")) {
    const name = params.get("village") || "";
    if (!name) path += "&village_id=is.null";
    else {
      const village = await villageByName(env, name);
      path += village ? `&village_id=eq.${village.id}` : "&village_id=eq.00000000-0000-0000-0000-000000000000";
    }
  }
  const { body } = await db(env, path);
  return body || [];
}

async function indexStatus(env) {
  const docs = await documents(env, new URLSearchParams());
  const villages = await listVillages(env);
  const ready = docs.filter(d => d.status === "ready");
  const processing = docs.find(d => d.status === "processing");
  const failed = docs.find(d => d.status === "failed" || d.status === "needs_review");
  return {
    status: processing ? "indexing" : failed ? "error" : ready.length ? "ready" : "empty",
    version: ready.length,
    last_indexed_at: null,
    last_duration_sec: null,
    error: failed?.error_message || null,
    total_pdfs: docs.length,
    indexed_pdfs: ready.length,
    total_records: ready.reduce((n, d) => n + (d.record_count || 0), 0),
    total_villages: villages.length,
    ocr_available: true,
    progress: { current: 0, total: 0, percent: 0, file: processing?.original_filename || "", files_done: ready.length, files_total: docs.length },
  };
}

async function voterDetail(env, id) {
  const voterId = Number(id);
  if (!Number.isSafeInteger(voterId) || voterId < 1) return null;
  const { body: voters } = await db(env, `voters?select=id,document_id,village_id,record_index,name,relation_name,relation_type,epic,serial,house,age,gender,part,section,page&id=eq.${voterId}&limit=1`);
  const voter = voters?.[0];
  if (!voter) return null;
  const [{ body: documents }, { body: villages }] = await Promise.all([
    db(env, `documents?select=id,original_filename&id=eq.${voter.document_id}&limit=1`),
    db(env, `villages?select=id,name&id=eq.${voter.village_id}&limit=1`),
  ]);
  return {
    ...voter,
    pdf_name: documents?.[0]?.original_filename || "",
    village: villages?.[0]?.name || "",
  };
}

async function handle(request, env) {
  const url = new URL(request.url);
  const p = url.pathname.replace(/\/+$/, "") || "/";

  if (request.method === "GET" && p === "/api/villages")
    return json({ villages: await listVillages(env) });

  if (request.method === "GET" && p === "/api/stats") {
    const s = await indexStatus(env);
    return json({ total_pdfs: s.total_pdfs, total_records: s.total_records, total_villages: s.total_villages, index_status: s.status, index_version: s.version, last_indexed_at: s.last_indexed_at });
  }

  if (request.method === "GET" && p === "/api/search") {
    const started = Date.now();
    const searchText = url.searchParams.get("q") || "";
    const requestedPage = Math.max(1, Number(url.searchParams.get("page") || 1));
    const requestedSize = Math.min(100, Math.max(1, Number(url.searchParams.get("page_size") || 20)));
    const romanSearch = isRomanName(searchText);
    const villageName = url.searchParams.get("village") || "";
    const args = {
      search_text: searchText,
      village_name: villageName,
      page_number: requestedPage,
      page_size: requestedSize,
    };
    const body = romanSearch
      ? await englishCandidates(env, searchText, villageName)
      : (await db(env, "rpc/search_voters", { method: "POST", body: JSON.stringify(args) })).body;
    const result = romanSearch ? rerankEnglish(body, searchText, requestedPage, requestedSize) : body;
    result.took_ms = Date.now() - started;
    return json(result);
  }

  if (request.method === "GET" && p === "/api/suggest") {
    const searchText = url.searchParams.get("q") || "";
    const villageName = url.searchParams.get("village") || "";
    const limit = Math.min(20, Number(url.searchParams.get("limit") || 8));
    if (isRomanName(searchText)) {
      const body = await englishCandidates(env, searchText, villageName);
      const ranked = rerankEnglish(body, searchText, 1, limit).results;
      const items = ranked.map(item => ({
        text: item.name, name: item.name, relation_name: item.relation_name,
        relation_type: item.relation_type, village: item.village, pdf: item.pdf,
        page: item.page, age: item.age, gender: item.gender,
      }));
      return json({ items, suggestions: items.map(item => item.text), transliterated: rerankEnglish(body, searchText, 1, limit).query.transliterated });
    }
    const args = { search_text: searchText, village_name: villageName, result_limit: limit };
    const { body } = await db(env, "rpc/suggest_voters", { method: "POST", body: JSON.stringify(args) });
    return json({ items: body || [], suggestions: (body || []).map(x => x.text) });
  }

  const voterMatch = p.match(/^\/api\/voters\/(\d+)(?:\/(locator))?$/);
  if (request.method === "GET" && voterMatch) {
    const voter = await voterDetail(env, voterMatch[1]);
    if (!voter) return json({ detail: "Voter not found" }, 404);
    if (!voterMatch[2]) return json(voter);

    const { body: peers } = await db(
      env,
      `voters?select=id,record_index,serial&document_id=eq.${voter.document_id}&page=eq.${voter.page}&order=record_index.asc`,
    );
    const records = peers || [];
    const ordinal = Math.max(0, records.findIndex(item => item.id === voter.id));
    const serials = records.map(item => Number.parseInt(item.serial, 10)).filter(Number.isFinite);
    const currentSerial = Number.parseInt(voter.serial, 10);
    const serialSlot = Number.isFinite(currentSerial) && serials.length
      ? currentSerial - Math.min(...serials)
      : -1;
    const slot = serialSlot >= 0 && serialSlot < 30 ? serialSlot : ordinal;
    const column = slot % 3;
    const row = Math.floor(slot / 3);
    return json({
      voter_id: voter.id,
      name: voter.name,
      page: voter.page,
      serial: voter.serial,
      slot,
      box: {
        x: 0.021 + column * 0.326,
        y: 0.072 + row * 0.088,
        width: 0.306,
        height: 0.083,
      },
    });
  }

  if (request.method === "GET" && p === "/api/admin/villages") {
    return json({ villages: await listVillages(env), unassigned_pdfs: 0 });
  }

  if (request.method === "POST" && p === "/api/admin/villages") {
    const input = await request.json();
    const name = String(input.name || "").trim();
    if (!name) return json({ detail: "Village name is required" }, 400);
    const { body } = await db(env, "villages", { method: "POST", body: JSON.stringify({ name, slug: slug(name) }) });
    return json({ name: body[0].name });
  }

  if (request.method === "POST" && p === "/api/admin/villages/rename") {
    const input = await request.json();
    const village = await villageByName(env, input.old_name);
    if (!village) return json({ detail: "Village not found" }, 404);
    await db(env, `villages?id=eq.${village.id}`, { method: "PATCH", body: JSON.stringify({ name: String(input.new_name).trim(), slug: slug(input.new_name) }) });
    return json({ old_name: input.old_name, new_name: input.new_name });
  }

  if (request.method === "DELETE" && p.startsWith("/api/admin/villages/")) {
    const name = decodeURIComponent(p.slice("/api/admin/villages/".length));
    const village = await villageByName(env, name);
    if (!village) return json({ detail: "Village not found" }, 404);
    const docs = await documents(env, new URLSearchParams({ village: name }));
    for (const d of docs) await env.PDF_BUCKET.delete(d.r2_key);
    await db(env, `villages?id=eq.${village.id}`, { method: "DELETE" });
    return json({ deleted: name, removed_pdfs: docs.map(d => d.id) });
  }

  if (request.method === "GET" && p === "/api/admin/pdfs") {
    const docs = await documents(env, url.searchParams);
    return json({ pdfs: docs.map(pdfJson), index: await indexStatus(env) });
  }

  if (request.method === "GET" && p === "/api/admin/duplicates") {
    const { body } = await db(env, "rpc/admin_duplicate_voters", { method: "POST", body: "{}" });
    let cross = { same_relative: [], different_relative: [], setup_required: false };
    try {
      const { body: crossBody } = await db(env, "rpc/admin_cross_village_duplicates", { method: "POST", body: "{}" });
      cross = { ...cross, ...crossBody };
    } catch (error) {
      // Keep the existing review available while migration 0005 is being applied.
      if (/PGRST202|Could not find the function/i.test(String(error))) {
        cross.setup_required = true;
      } else {
        throw error;
      }
    }
    return json({ ...(body || { epic: [], name: [] }), ...cross });
  }

  if (request.method === "POST" && p === "/api/admin/pdfs/upload") {
    const form = await request.formData();
    const villageName = String(form.get("village") || "").trim();
    const village = await ensureVillage(env, villageName);
    const files = form.getAll("files").filter(v => typeof v !== "string");
    const saved = [], errors = [];
    for (const file of files) {
      try {
        if (!file.name.toLowerCase().endsWith(".pdf")) throw new Error("Only PDF files are accepted");
        const id = crypto.randomUUID();
        const key = `${slug(villageName)}/${id}-${safeName(file.name)}`;
        const object = await env.PDF_BUCKET.put(key, file.stream(), { httpMetadata: { contentType: "application/pdf" } });
        const row = { id, village_id: village?.id || null, original_filename: safeName(file.name), r2_key: key, r2_etag: object.etag, size_bytes: file.size, status: "uploaded", active: false };
        const { body } = await db(env, "documents", { method: "POST", body: JSON.stringify(row) });
        saved.push(pdfJson({ ...body[0], villages: village ? { name: village.name } : null }));
      } catch (e) { errors.push({ file: file.name, error: e.message }); }
    }
    if (!saved.length && errors.length) return json({ detail: errors }, 400);
    return json({ saved, errors });
  }

  if (request.method === "POST" && p === "/api/admin/pdfs/replace") {
    const form = await request.formData();
    const id = String(form.get("id") || "");
    const file = form.get("file");
    const { body } = await db(env, `documents?select=id,r2_key,village_id,villages(name)&id=eq.${encodeURIComponent(id)}&limit=1`);
    if (!body?.length || !file || typeof file === "string") return json({ detail: "PDF or replacement file not found" }, 404);
    if (!file.name.toLowerCase().endsWith(".pdf")) return json({ detail: "Only PDF files are accepted" }, 400);
    const doc = body[0];
    await env.PDF_BUCKET.put(doc.r2_key, file.stream(), { httpMetadata: { contentType: "application/pdf" } });
    await db(env, `documents?id=eq.${doc.id}`, { method: "PATCH", body: JSON.stringify({ original_filename: safeName(file.name), size_bytes: file.size, status: "uploaded", active: false, error_message: null }) });
    return json(pdfJson({ ...doc, original_filename: safeName(file.name), size_bytes: file.size, status: "uploaded" }));
  }

  if (request.method === "DELETE" && p === "/api/admin/pdfs") {
    const id = url.searchParams.get("id");
    const { body } = await db(env, `documents?select=id,r2_key&id=eq.${encodeURIComponent(id)}&limit=1`);
    if (!body?.length) return json({ detail: "PDF not found" }, 404);
    await env.PDF_BUCKET.delete(body[0].r2_key);
    await db(env, `documents?id=eq.${body[0].id}`, { method: "DELETE" });
    return json({ deleted: id });
  }

  if (request.method === "POST" && p === "/api/admin/pdfs/rename") {
    const input = await request.json();
    await db(env, `documents?id=eq.${encodeURIComponent(input.id)}`, { method: "PATCH", body: JSON.stringify({ original_filename: safeName(input.new_name) }) });
    return json({ old_id: input.id, new_id: input.id });
  }

  if (request.method === "POST" && p === "/api/admin/pdfs/move") {
    const input = await request.json();
    const village = input.village ? await villageByName(env, input.village) : null;
    if (input.village && !village) return json({ detail: "Village not found" }, 400);
    await db(env, `documents?id=eq.${encodeURIComponent(input.id)}`, { method: "PATCH", body: JSON.stringify({ village_id: village?.id || null, status: "uploaded", active: false }) });
    return json({ old_id: input.id, new_id: input.id });
  }

  if (request.method === "POST" && p === "/api/admin/pdfs/retry") {
    const input = await request.json();
    const id = encodeURIComponent(String(input.id || ""));
    const { body } = await db(env, `documents?select=id,status,village_id&id=eq.${id}&limit=1`);
    const document = body?.[0];
    if (!document) return json({ detail: "PDF not found" }, 404);
    if (!document.village_id) return json({ detail: "Assign a village before indexing" }, 400);
    if (!["failed", "needs_review"].includes(document.status)) {
      return json({ detail: "Only failed or review PDFs can be retried" }, 409);
    }
    await db(env, `documents?id=eq.${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "queued", active: false, error_message: null, quality_report: null }),
    });
    return json({ id: input.id, status: "queued" });
  }

  if (request.method === "GET" && p === "/api/admin/index/status") return json(await indexStatus(env));
  if (request.method === "POST" && p === "/api/admin/index/rebuild") {
    await db(env, "documents?status=eq.ready", { method: "PATCH", body: JSON.stringify({ status: "queued", active: false }) });
    return json(await indexStatus(env));
  }

  if ((request.method === "GET" || request.method === "HEAD") && (p.startsWith("/pdf/view/") || p.startsWith("/pdf/download/"))) {
    const id = decodeURIComponent(p.split("/").pop());
    const { body } = await db(env, `documents?select=original_filename,r2_key&id=eq.${encodeURIComponent(id)}&limit=1`);
    if (!body?.length) return json({ detail: "PDF not found" }, 404);
    const object = request.method === "HEAD"
      ? await env.PDF_BUCKET.head(body[0].r2_key)
      : await env.PDF_BUCKET.get(body[0].r2_key, { range: request.headers });
    if (!object) return json({ detail: "PDF object not found" }, 404);
    const disposition = p.includes("/download/") ? "attachment" : "inline";
    const headers = new Headers({
      "content-type": "application/pdf",
      "content-disposition": `${disposition}; filename*=UTF-8''${encodeURIComponent(body[0].original_filename)}`,
      "accept-ranges": "bytes",
      etag: object.httpEtag,
    });
    let status = 200;
    if (object.range) {
      const start = object.range.offset || 0;
      const length = object.range.length || object.size;
      headers.set("content-range", `bytes ${start}-${start + length - 1}/${object.size}`);
      headers.set("content-length", String(length));
      status = 206;
    } else {
      headers.set("content-length", String(object.size));
    }
    return new Response(request.method === "HEAD" ? null : object.body, { status, headers });
  }

  return json({ detail: "Not found" }, 404);
}

export default {
  async fetch(request, env) {
    const headers = cors(env);
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers });
    try {
      const response = await handle(request, env);
      Object.entries(headers).forEach(([k, v]) => response.headers.set(k, v));
      return response;
    } catch (e) {
      return json({ detail: e.message || "Unexpected server error" }, 500, headers);
    }
  },
};

export { englishNameMatch, rerankEnglish };
