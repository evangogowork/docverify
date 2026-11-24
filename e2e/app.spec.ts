import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(import.meta.dirname, "..");
const anchors = JSON.parse(fs.readFileSync(path.join(ROOT, "frontend/src/generated/anchors.json"), "utf8"));

async function loginPlatform(page: Page, platform = "ecommerce") {
  await page.goto("/login");
  await page.locator('select[name="client_id"]').selectOption(`${platform}-demo`);
  await page.locator('input[name="secret"]').fill(`demo-secret-${platform}`);
  await page.getByRole("button", { name: "登录" }).last().click();
  await expect(page.getByRole("heading", { name: "提交证明材料" })).toBeVisible();
}

test("platform submits a clean sample and it is auto-approved, with a signed callback", async ({ page }) => {
  await loginPlatform(page);
  await page.locator('select[name="sample"]').selectOption("clean");
  await page.getByTestId("submit-sample").click();
  await expect(page).toHaveURL(/\/cases\/case_/);
  await expect(page.locator("h1").getByTestId("state")).toHaveText("APPROVED");
  await expect(page.getByText("business_name").first()).toBeVisible();
  await expect(page.locator("table").last()).toContainText("APPROVED", { timeout: 60_000 });
  const caseId = page.url().split("/").pop()!;
  await page.getByRole("link", { name: "平台回调" }).click();
  const row = page.locator("tr", { hasText: caseId }).filter({ hasText: "APPROVED" });
  await expect(row).toContainText("ok");
});

test("low-resolution scan goes to human review; reviewer claims it and asks for resubmission; platform resubmits", async ({ page, browser }) => {
  await loginPlatform(page);
  await page.locator('select[name="sample"]').selectOption("lowres");
  await page.getByTestId("submit-sample").click();
  await expect(page.locator("h1").getByTestId("state")).toHaveText("IN_REVIEW");
  const caseId = page.url().split("/").pop()!;

  const reviewer = await (await browser.newContext()).newPage();
  await reviewer.goto("/login");
  await reviewer.getByRole("button", { name: "审核员" }).click();
  await reviewer.locator('input[name="username"]').fill("reviewer");
  await reviewer.locator('input[name="secret"]').fill("reviewer-demo-pass");
  await reviewer.getByRole("button", { name: "登录" }).last().click();
  await expect(reviewer.getByRole("heading", { name: "审核队列" })).toBeVisible();
  await expect(reviewer.locator("tr", { hasText: caseId })).toBeVisible();
  // Claim until we get our case (other cases may be ahead of it in the heap).
  for (let i = 0; i < 20; i++) {
    await reviewer.goto("/review");
    await reviewer.getByTestId("claim-next").click();
    await expect(reviewer).toHaveURL(/\/review\/case_/);
    if (reviewer.url().endsWith(caseId)) break;
    await reviewer.locator('select[name="decision"]').selectOption("RESUBMIT_REQUESTED");
    await reviewer.getByTestId("submit-decision").click();
  }
  expect(reviewer.url()).toContain(caseId);
  await expect(reviewer.locator("img.doc")).toBeVisible();
  await expect(reviewer.getByText("失败项")).toBeVisible();
  await reviewer.locator('select[name="decision"]').selectOption("RESUBMIT_REQUESTED");
  await reviewer.getByTestId("submit-decision").click();
  await expect(reviewer.locator("h1").getByTestId("state")).toHaveText("RESUBMIT_REQUESTED");

  await page.reload();
  await expect(page.getByText("需要重新提交")).toBeVisible();
  const sample = await page.request.get(`/v1/samples/clean?account_id=acct_1001&doc_type=business_license`);
  await page.locator('input[name="resubmit-file"]').setInputFiles({ name: "rescan.png", mimeType: "image/png", buffer: await sample.body() });
  await page.getByRole("button", { name: "重新提交" }).click();
  await expect(page.locator("h1").getByTestId("state")).toHaveText("APPROVED");
  await expect(page.getByText("第 2 轮")).toBeVisible();
});

test("learn mode: stages light up in order with real data and pinned source links", async ({ page }) => {
  await page.goto("/learn");
  await page.locator("#learn-scenario").selectOption("lowres");
  await page.locator("#learn-submit").click();
  const order = ["upload", "s3", "lambda", "sqs", "extraction", "validation", "decision"];
  for (const id of order) await expect(page.locator(`li[data-stage="${id}"]`)).toHaveAttribute("data-status", "done");
  await expect(page.locator('li[data-stage="review"]')).toHaveAttribute("data-status", "active");
  // Real data: the Lambda's own CloudWatch log line and the SQS receipt with the account's message group.
  await page.locator('li[data-stage="lambda"]').click();
  await expect(page.locator("#stage-detail")).toContainText('"queued"');
  await page.locator('li[data-stage="sqs"]').click();
  await expect(page.locator('#stage-detail code[data-hl="group-id"]').first()).toHaveText("acct_1002");
  await page.locator('#stage-detail details[data-json="sqs-body-0"] > summary').click();
  await expect(page.locator('#stage-detail details[data-json="sqs-body-0"] pre')).toContainText('"account_id": "acct_1002"');
  // Act as the reviewer, then watch decision + callback complete.
  await page.locator('li[data-stage="review"]').click();
  await page.locator("#learn-approve").click();
  await expect(page.locator('li[data-stage="review"]')).toHaveAttribute("data-status", "done");
  await expect(page.locator('li[data-stage="callback"]')).toHaveAttribute("data-status", "done");
  // Idempotency: replay a duplicate message; the worker drops it via the Redis done key.
  await page.locator("#learn-replay").click();
  await expect(page.getByTestId("receipt-outcome").last()).toHaveText("dedup:done");
  // Source links are pinned to a commit and point at the anchored lines.
  await page.locator('li[data-stage="extraction"]').click();
  const link = page.locator('#stage-detail a[data-anchor="ocr"]');
  const href = await link.getAttribute("href");
  const a = anchors["ocr"];
  expect(href).toMatch(new RegExp(`^https://github\\.com/evangogowork/docverify/blob/[0-9a-f]{7,40}/${a.path.replace(/[.]/g, "\\.")}#L${a.start}-L${a.end}$`));
  const lines = fs.readFileSync(path.join(ROOT, a.path), "utf8").split("\n");
  expect(lines[a.start - 1]).toContain("@learn:" + "ocr");
  // Per-stage video slot: plays the part's video, or says it is not generated yet.
  await page.locator('.video-btn[data-part="p04-extract"]').click();
  await expect(page.getByTestId("video").or(page.getByTestId("video-missing"))).toBeVisible();
  // Eval panel
  await page.locator("#learn-eval").click();
  await expect(page.getByTestId("gate")).toHaveText("通过");
});

test("interview tab: open a question and see its answer", async ({ page }) => {
  await page.goto("/learn/interview");
  const first = page.locator("details.qa").first();
  await expect(first).toBeVisible();
  await first.locator("summary").click();
  await expect(first.locator(".answer")).toContainText("一句话答案");
});

test("problems tab: expand a problem, see its symptom, fix and source links", async ({ page }) => {
  await page.goto("/learn");
  await page.locator("#tab-problems").click();
  await expect(page).toHaveURL(/\/learn\/problems$/);
  const q = page.locator('details.problem[data-problem="q10"]');
  await q.locator("summary").click();
  await expect(q.locator(".answer")).toContainText("怎么定位");
  await expect(q.locator('a[data-anchor="scan-paginated"]')).toHaveAttribute("href", /blob\/[0-9a-f]{7,40}\/docverify\/cases\.py#L\d+-L\d+$/);
  await q.locator("[data-problem-video]").click();
  await expect(q.getByTestId("video").or(q.getByTestId("video-missing"))).toBeVisible();
});
