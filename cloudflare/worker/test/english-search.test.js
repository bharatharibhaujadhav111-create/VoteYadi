import assert from "node:assert/strict";
import test from "node:test";

import { englishNameMatch, rerankEnglish } from "../src/index.js";

test("first-name and full-prefix matches outrank middle-name matches", () => {
  const prefix = englishNameMatch("Bharat Jadhav", "भारत जाधव पाटील");
  const first = englishNameMatch("Bharat Jadhav", "भारत राम जाधव");
  const middle = englishNameMatch("Bharat Jadhav", "सुरेश भारत जाधव");
  const unordered = englishNameMatch("Bharat Jadhav", "सुरेश जाधव भारत");

  assert.equal(prefix.tier, 6);
  assert.equal(first.tier, 5);
  assert.equal(middle.tier, 4);
  assert.equal(unordered.tier, 3);
  assert.ok(prefix.score > first.score && first.score > middle.score);
});

test("single first-name match outranks the same token in a middle name", () => {
  assert.ok(
    englishNameMatch("Bharat", "भारत विठ्ठल जाधव").score
      > englishNameMatch("Bharat", "विठ्ठल भारत जाधव").score,
  );
});

test("ranking paginates after ordering all matching personal names", () => {
  const body = {
    results: [
      { id: 1, name: "सुरेश भारत जाधव" },
      { id: 2, name: "भारत जाधव पाटील" },
      { id: 3, name: "गणेश पाटील", relation_name: "भारत पाटील" },
      { id: 4, name: "भारत राम जाधव" },
      { id: 5, name: "सुरेश जाधव भारत" },
    ],
  };

  const firstPage = rerankEnglish(body, "Bharat Jadhav", 1, 2);
  const secondPage = rerankEnglish(body, "Bharat Jadhav", 2, 2);
  assert.deepEqual(firstPage.results.map(row => row.id), [2, 4]);
  assert.deepEqual(secondPage.results.map(row => row.id), [1, 5]);
  assert.equal(firstPage.total, 4);
});
