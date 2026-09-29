import assert from "node:assert/strict";
import test from "node:test";

import { englishNameMatch, inferredMarathiQuery, rerankEnglish } from "../src/index.js";

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
