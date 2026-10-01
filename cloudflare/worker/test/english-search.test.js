import assert from "node:assert/strict";
import test from "node:test";

import worker, { englishNameMatch, inferredMarathiQuery, rerankEnglish } from "../src/index.js";

test("Vijaysinh exactly matches the Marathi first-name token", () => {
  const first = englishNameMatch("Vijaysinh", "विजयसिंह भारत जाधव");
  const middle = englishNameMatch("Vijaysinh", "सोनाली विजयसिंह मल्लाव");
  assert.equal(first.score, 100);
  assert.equal(first.tier, 6);
  assert.equal(middle.tier, 4);
});

test("candidate results recover the printed Marathi query", () => {
  assert.equal(inferredMarathiQuery("Vijaysinh", [
    { name: "सोनाली विजयसिंह मल्लाव", relation_name: "विजयसिंह मल्लाव" },
  ]), "विजयसिंह");
});

test("first-name and full-prefix matches outrank middle-name matches", () => {
  const prefix = englishNameMatch("Bharat Jadhav", "भारत जाधव पाटील");
  const first = englishNameMatch("Bharat Jadhav", "भारत राम जाधव");
  const middle = englishNameMatch("Bharat Jadhav", "सुरेश भारत जाधव");
  const unordered = englishNameMatch("Bharat Jadhav", "सुरेश जाधव भारत");

  assert.equal(prefix.tier, 6);
  assert.equal(first.tier, 5);
  assert.equal(middle.tier, 4);
  assert.equal(unordered.tier, 3);
  assert.ok(prefix.tier > first.tier && first.tier > middle.tier);
});

test("single first-name match outranks the same token in a middle name", () => {
  assert.ok(englishNameMatch("Bharat", "भारत विठ्ठल जाधव").tier
    > englishNameMatch("Bharat", "विठ्ठल भारत जाधव").tier);
});

test("ranking keeps relative-name matches after every personal-name match", () => {
  const body = {
    results: [
      { id: 1, name: "सुरेश भारत जाधव" },
      { id: 2, name: "भारत जाधव पाटील" },
      { id: 3, name: "गणेश पाटील", relation_name: "भारत जाधव" },
      { id: 4, name: "भारत राम जाधव" },
      { id: 5, name: "सुरेश जाधव भारत" },
    ],
  };

  const firstPage = rerankEnglish(body, "Bharat Jadhav", 1, 2);
  const secondPage = rerankEnglish(body, "Bharat Jadhav", 2, 2);
  const thirdPage = rerankEnglish(body, "Bharat Jadhav", 3, 2);
  assert.deepEqual(firstPage.results.map(row => row.id), [2, 4]);
  assert.deepEqual(secondPage.results.map(row => row.id), [1, 5]);
  assert.deepEqual(thirdPage.results.map(row => row.id), [3]);
  assert.equal(firstPage.total, 5);
});

test("a weak own-name match still precedes an exact relative-name match", () => {
  const body = {
    results: [
      { id: 1, name: "विजयसिंह पाटील", relation_name: "भारत जाधव" },
      { id: 2, name: "विजयसिंह भारत जाधव", relation_name: "गणेश पाटील" },
    ],
  };
  assert.deepEqual(
    rerankEnglish(body, "Bharat Jadhav", 1, 10).results.map(row => row.id),
    [2, 1],
  );
});

test("Marathi voter-name matches rank before Marathi relative-name matches", () => {
  const body = {
    results: [
      { id: 1, name: "भगवंत भारत ढगे", relation_name: "भारत ढगे" },
      { id: 2, name: "सुनीता ढगे", relation_name: "भारत ढगे" },
      { id: 3, name: "भारत अरविंद गवळी", relation_name: "अरविंद गवळी" },
      { id: 4, name: "भारत तुकाराम कांबळे", relation_name: "तुकाराम कांबळे" },
    ],
  };

  const ranked = rerankEnglish(body, "भारत", 1, 10);
  assert.deepEqual(ranked.results.map(row => row.id), [3, 4, 1, 2]);
  assert.equal(ranked.query.script, "devanagari");
});

test("every word in a multi-word query must match the same name field", () => {
  const body = {
    results: [
      { id: 1, name: "प्रताप जाधव", relation_name: "महादेव जाधव" },
      { id: 2, name: "भारत लिंबा जाधव", relation_name: "लिंबा जाधव" },
      { id: 3, name: "संध्या पाटील", relation_name: "भारत जाधव" },
    ],
  };

  assert.deepEqual(
    rerankEnglish(body, "Bharat Jadhav", 1, 10).results.map(row => row.id),
    [2, 3],
  );
});

test("an exact EPIC match remains searchable", () => {
  const body = {
    results: [{ id: 1, name: "सोनाली मल्लाव", relation_name: "विजयसिंह मल्लाव", epic: "ABC1234567" }],
  };
  assert.deepEqual(rerankEnglish(body, "abc1234567", 1, 10).results.map(row => row.id), [1]);
});

test("live search route uses one ranked database RPC", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), body: JSON.parse(init.body) });
    return new Response(JSON.stringify({
      results: [{ id: 7, name: "भरत जाधव", relation_name: "गणपती जाधव" }],
      total: 100,
      page: 1,
      page_size: 10,
      query: { text: "bharat jadhav" },
    }), { status: 200, headers: { "content-type": "application/json" } });
  };
  try {
    const response = await worker.fetch(
      new Request("https://api.test/api/search?q=bharat%20jadhav&page=1&page_size=10"),
      { SUPABASE_URL: "https://database.test", SUPABASE_SECRET_KEY: "test-secret" },
      { waitUntil() {} },
    );
    const body = await response.json();
    assert.equal(response.status, 200);
    assert.equal(body.results[0].name, "भरत जाधव");
    assert.equal(calls.length, 1);
    assert.match(calls[0].url, /rpc\/search_voters_ranked$/);
    assert.deepEqual(calls[0].body, {
      search_text: "bharat jadhav",
      village_name: "",
      page_number: 1,
      page_size: 10,
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("rare English spelling uses only one bounded Marathi expansion", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (_url, init) => {
    const args = JSON.parse(init.body);
    calls.push(args);
    const english = args.search_text === "vijaysinh";
    return new Response(JSON.stringify({
      results: english
        ? [{ id: 1, name: "विजयसिंह गरड", relation_name: "दिनकर गरड" }]
        : [
            { id: 1, name: "विजयसिंह गरड", relation_name: "दिनकर गरड" },
            { id: 2, name: "विजयसिंह भारत जाधव", relation_name: "भारत जाधव" },
          ],
      total: english ? 1 : 2,
      page: 1,
      page_size: args.page_size,
      query: { text: args.search_text },
    }), { status: 200, headers: { "content-type": "application/json" } });
  };
  try {
    const response = await worker.fetch(
      new Request("https://api.test/api/search?q=vijaysinh&page=1&page_size=10"),
      { SUPABASE_URL: "https://database.test", SUPABASE_SECRET_KEY: "test-secret" },
      { waitUntil() {} },
    );
    const body = await response.json();
    assert.equal(response.status, 200);
    assert.deepEqual(body.results.map(row => row.id), [1, 2]);
    assert.equal(calls.length, 2);
    assert.equal(calls[0].search_text, "vijaysinh");
    assert.equal(calls[1].search_text, "विजयसिंह");
    assert.equal(calls[1].page_size, 100);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
