import { describe, expect, it } from "vitest";
import { addApplicationAnswer, savedApplicationAnswer, quickApplyRetryHref, quickApplyInitialUrls } from "./applicationAnswers";

const question = { company: "Example", question: "Do you hold certification?", source_url: "https://www.indeed.com/viewjob?jk=abc" };

describe("application answers", () => {
  it("preserves existing rules and scopes the answer to the company and exact question", () => {
    const result = addApplicationAnswer("US citizen. Minimum base $220,000.", question, " No ");
    expect(result).toContain("US citizen. Minimum base $220,000.");
    expect(result).toContain('"company":"Example"');
    expect(result).toContain('"question":"Do you hold certification?"');
    expect(result).toContain('"answer":"No"');
  });
  it("replaces a previous answer to that question without changing another employer's answer", () => {
    const first = addApplicationAnswer("Existing rules", { ...question, company: "Other" }, "Yes");
    const second = addApplicationAnswer(first, question, "Yes");
    const updated = addApplicationAnswer(second, question, "No");
    expect(updated.match(/user-confirmed/g)).toHaveLength(2);
    expect(updated).toContain('"company":"Other"');
    expect(updated).toContain('"answer":"Yes"');
    expect(addApplicationAnswer(updated, question, "No")).toBe(updated);
  });
  it("rejects empty answers and overflow instead of silently truncating rules", () => {
    expect(() => addApplicationAnswer("rules", question, "  ")).toThrow("Enter an answer");
    expect(() => addApplicationAnswer("x".repeat(20000), question, "No")).toThrow("Settings");
  });
  it("recovers saved answers after reload without applying them to a different question or employer", () => {
    const rules = addApplicationAnswer("Other rules", question, "No");
    expect(savedApplicationAnswer(rules, question)).toBe("No");
    expect(savedApplicationAnswer(rules, { ...question, company: "Other" })).toBeNull();
    expect(savedApplicationAnswer(rules, { ...question, question: "Different question?" })).toBeNull();
  });
});

describe("single-job retry", () => {
  it("replaces old saved job URLs with exactly the selected Indeed source URL", () => {
    const href = quickApplyRetryHref(question.source_url)!;
    expect(quickApplyInitialUrls(href.slice(href.indexOf("?")), "https://old.example\nhttps://other.example")).toBe(question.source_url);
  });
  it("restores saved URLs only when no retry was requested", () => {
    expect(quickApplyInitialUrls("", "saved")).toBe("saved");
    expect(quickApplyInitialUrls("?retry_job=javascript%3Aalert(1)", "saved")).toBe("");
  });
  it("rejects multiline, credentialed, and non-Indeed retry destinations", () => {
    for (const url of ["javascript:alert(1)", "https://indeed.com.evil.test/a", "https://user@indeed.com/a", `${question.source_url}\nhttps://indeed.com/b`]) {
      expect(quickApplyRetryHref(url)).toBeNull();
    }
  });
});
