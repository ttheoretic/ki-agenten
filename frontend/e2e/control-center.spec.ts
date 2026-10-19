import { expect, test } from "@playwright/test";

const TOKEN = "e2e-token-1234567890";
const auth = { Authorization: `Bearer ${TOKEN}` };

async function waitForRunEnd(request: import("@playwright/test").APIRequestContext) {
  await expect.poll(async () => {
    const s = await (await request.get("/api/state", { headers: auth })).json();
    return s.active_run === null && s.server.run_thread_busy === false && s.last_run !== null;
  }, { timeout: 30_000 }).toBe(true);
}

test("Unternehmenszentrale zeigt echten Backend-Zustand, Kommunikation, Freigaben und Steuerung", async ({ page, request }) => {
  // Ohne Token: Login statt Daten
  await page.goto("/");
  await expect(page.getByText("Bitte das Owner-Token eingeben")).toBeVisible();

  await page.goto(`/#token=${TOKEN}`);
  await expect(page.getByTestId("conn-status")).toContainText("Live verbunden");
  // Vor dem ersten Lauf: keine erfundenen Daten
  await expect(page.getByTestId("company-status")).toContainText("Wartet auf ersten Lauf");
  await expect(page.getByTestId("revenue")).toHaveText("Noch keine Daten");
  await expect(page.getByTestId("progress")).toHaveText("Noch keine Daten");
  await expect(page.locator("[data-testid^=agent-]")).toHaveCount(11);
  await expect(page.getByTestId("agent-ceo")).toHaveAttribute("data-status", "idle");
  await expect(page.getByTestId("active-edges")).toHaveText("keine aktive Kommunikation");
  expect(page.url()).not.toContain(TOKEN); // Token wird aus der Adresszeile entfernt

  // Lauf über die Oberfläche starten → Live-Ereignisse und echte Statuswechsel
  await page.getByTestId("btn-run").click();
  await expect(page.getByTestId("feed-item").first()).toBeVisible();
  await waitForRunEnd(request);
  await expect(page.getByTestId("selected-idea")).toContainText("Angebots");
  await expect(page.getByTestId("agent-research")).toHaveAttribute("data-status", /done|communicating/);
  await expect(page.locator("[data-active=true]").first()).toBeVisible(); // echte, frische Übergabe wird animiert
  const feedCount = await page.getByTestId("feed-item").count();
  expect(feedCount).toBeGreaterThan(20);

  // Agenten-Detail
  await page.getByTestId("agent-builder").click();
  await expect(page.getByTestId("agent-panel")).toContainText("local_static_checks");
  await expect(page.getByTestId("agent-panel")).toContainText("Forge");
  await page.keyboard.press("Escape");

  // Verbindung anklicken → Details der tatsächlichen Kommunikation
  await page.locator("[data-testid=edge-ceo-research] .edge-hit").dispatchEvent("click");
  await expect(page.getByTestId("edge-panel")).toContainText("Auftrag");
  await expect(page.getByTestId("edge-panel")).toContainText("Absender");
  await page.keyboard.press("Escape");

  // Ereignis im Aktivitätsprotokoll anklicken
  await page.getByTestId("feed-item").first().click();
  await expect(page.getByTestId("event-panel")).toContainText("Ereignis #");
  await page.keyboard.press("Escape");

  // Zweiter Lauf bis zur Launch-Vorbereitung → Freigabeantrag
  expect((await request.post("/api/runs", { headers: auth })).ok()).toBeTruthy();
  await waitForRunEnd(request);
  await page.getByTestId("tab-approvals").click();
  const card = page.locator("[data-testid^=approval-A-]").filter({ hasText: "Landingpage veröffentlichen" });
  await expect(card).toBeVisible();
  await expect(card.getByTestId("approval-status")).toHaveText("Offen");
  await card.getByTestId("btn-approve").click();
  await card.getByTestId("btn-approve-confirm").click();
  await expect(card.getByTestId("approval-status")).toHaveText("Genehmigt");
  await expect(card.getByTestId("execution-status")).toHaveText("Erfolgreich ausgeführt");
  await expect(card.getByTestId("btn-approve")).toHaveCount(0); // keine zweite Genehmigung möglich
  const approvals = await (await request.get("/api/approvals", { headers: auth })).json();
  const id = approvals.find((a: { action_type: string }) => a.action_type === "publish_website").id;
  const again = await request.post(`/api/approvals/${id}/decision`, { headers: auth, data: { decision: "approve", params_hash: "x" } });
  expect(again.status()).toBe(409);

  // Pausieren / Fortsetzen
  await page.getByTestId("btn-pause").click();
  await expect(page.getByTestId("company-status")).toContainText("Pausiert");
  await expect(page.getByTestId("btn-run")).toBeDisabled();
  await page.getByTestId("btn-resume").click();
  await expect(page.getByTestId("company-status")).not.toContainText("Pausiert");

  // Teamarbeit: Agenten haben sich gegenseitig geholfen (echte Ereignisse aus dem Lauf)
  await page.getByTestId("tab-team").click();
  await expect(page.getByTestId("teamwork")).toContainText("Ledger");

  // Kennzahlen: ohne Messung keine Daten
  await page.getByTestId("tab-metrics").click();
  await expect(page.getByTestId("no-metrics")).toBeVisible();
});

test("API verweigert Zugriff ohne Token", async ({ request }) => {
  expect((await request.get("/api/state")).status()).toBe(401);
  expect((await request.post("/api/control/stop")).status()).toBe(401);
});
