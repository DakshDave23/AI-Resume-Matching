import { describe, expect, it } from "vitest";

import { progressOf, type Batch } from "@/api/batches";
import { checkFiles, formatSize, MAX_FILES } from "@/lib/files";

function file(name: string, bytes = 1000): File {
  return new File([new Uint8Array(bytes)], name);
}

describe("checkFiles", () => {
  it("accepts PDF and DOCX in any case", () => {
    const { accepted, rejected } = checkFiles([file("a.pdf"), file("B.DOCX")], []);
    expect(accepted.map((f) => f.name)).toEqual(["a.pdf", "B.DOCX"]);
    expect(rejected).toEqual([]);
  });

  it.each([
    ["notes.txt", 10, "Only PDF and DOCX files can be uploaded."],
    ["old.doc", 10, "Only PDF and DOCX files can be uploaded."],
    ["empty.pdf", 0, "The file is empty."],
    ["huge.pdf", 5 * 1024 * 1024 + 1, "The file is larger than 5 MB."],
  ])("rejects %s with a reason", (name, bytes, reason) => {
    expect(checkFiles([file(name, bytes)], []).rejected).toEqual([{ name, reason }]);
  });

  it("allows exactly 5 MB", () => {
    expect(checkFiles([file("edge.pdf", 5 * 1024 * 1024)], []).accepted).toHaveLength(1);
  });

  it("skips a file already chosen, or dropped twice", () => {
    const cv = file("cv.pdf");
    expect(checkFiles([file("cv.pdf")], [cv]).rejected[0]?.reason).toBe(
      "This file is already in the list.",
    );
    expect(checkFiles([file("x.pdf"), file("x.pdf")], []).accepted).toHaveLength(1);
    expect(checkFiles([file("cv.pdf", 2000)], [cv]).accepted).toHaveLength(1); // same name, other file
  });

  it("stops at the batch limit", () => {
    const chosen = Array.from({ length: MAX_FILES - 1 }, (_, i) => file(`${i}.pdf`));
    const { accepted, rejected } = checkFiles([file("last.pdf"), file("extra.pdf")], chosen);
    expect(accepted.map((f) => f.name)).toEqual(["last.pdf"]);
    expect(rejected).toEqual([
      { name: "extra.pdf", reason: "At most 50 files can be uploaded at once." },
    ]);
  });
});

it("formats sizes", () => {
  expect([formatSize(512), formatSize(120_000), formatSize(3 * 1024 * 1024)]).toEqual([
    "512 B",
    "117 KB",
    "3.0 MB",
  ]);
});

describe("progressOf", () => {
  const batch = (status: string, parsed: number, failed: number, total = 15) =>
    ({ status, processed_files: parsed, failed_files: failed, total_files: total }) as Batch;

  it("counts processed files while parsing", () => {
    expect(progressOf(batch("processing", 7, 1))).toMatchObject({
      done: 8,
      percent: 53,
      finished: false,
      label: "8 of 15 processed",
    });
  });

  it("says how many parsed and failed when done", () => {
    expect(progressOf(batch("completed_with_errors", 14, 1))).toMatchObject({
      percent: 100,
      finished: true,
      label: "14 of 15 parsed, 1 failed",
    });
    expect(progressOf(batch("completed", 2, 0, 2)).label).toBe("2 of 2 parsed");
  });
});
