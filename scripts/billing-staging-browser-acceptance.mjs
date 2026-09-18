import { chromium } from "playwright";
import crypto from "node:crypto";

const BASE = "https://staging-api.terrasatch.com";
const runId = process.env.GITHUB_RUN_ID || Date.now().toString();
const email = `staging-acceptance-${runId}@example.com`;
const password = `TsA!${crypto.randomBytes(18).toString("base64url")}`;

function fail(message, extra = {}) {
  console.error(JSON.stringify({ ok: false, message, ...extra }, null, 2));
  process.exitCode = 1;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const text = await response.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    throw new Error(`Expected JSON from ${url}; status=${response.status}; body=${text.slice(0, 500)}`);
  }
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} from ${url}: ${JSON.stringify(data)}`);
  }
  return { response, data };
}

async function visibleLocatorInAnyFrame(page, selectors) {
  for (const frame of page.frames()) {
    for (const selector of selectors) {
      const locator = frame.locator(selector).first();
      try {
        if ((await locator.count()) > 0 && (await locator.isVisible())) {
          return locator;
        }
      } catch {
        // Frame may detach while Stripe transitions between steps.
      }
    }
  }
  return null;
}

async function fillAny(page, selectors, value, { optional = false } = {}) {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const locator = await visibleLocatorInAnyFrame(page, selectors);
    if (locator) {
      try {
        if (await locator.isEditable()) {
          await locator.fill(value);
          return true;
        }
        if (optional) return false;
      } catch {
        // Retry while Stripe mounts/re-mounts secure fields.
      }
    }
    await page.waitForTimeout(500);
  }
  if (optional) return false;
  throw new Error(`Unable to find an editable Stripe field: ${selectors.join(", ")}`);
}

async function clickSubmit(page) {
  const selectors = [
    'button[type="submit"]',
    'button:has-text("Start trial")',
    'button:has-text("Subscribe")',
    'button:has-text("Pay")',
    'button:has-text("Confirm")',
    'button:has-text("Continue")',
  ];
  for (let attempt = 0; attempt < 60; attempt += 1) {
    for (const frame of page.frames()) {
      for (const selector of selectors) {
        const locator = frame.locator(selector).first();
        try {
          if (
            (await locator.count()) > 0 &&
            (await locator.isVisible()) &&
            (await locator.isEnabled())
          ) {
            await locator.click();
            return;
          }
        } catch {
          // Retry through Checkout UI transitions.
        }
      }
    }
    await page.waitForTimeout(500);
  }
  throw new Error("Unable to find an enabled Stripe Checkout submit button");
}

async function main() {
  const checkoutBody = {
    display_name: "TerraSatch Staging Acceptance",
    email,
    organization_name: `TerraSatch Staging Acceptance ${runId}`,
    plan_code: "field",
    billing_interval: "monthly",
  };

  const { data: checkout } = await fetchJson(
    `${BASE}/api/v1/workspace/billing/checkout`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(checkoutBody),
    },
  );

  if (
    typeof checkout.checkout_url !== "string" ||
    !checkout.checkout_url.startsWith("https://buy.stripe.com/test_")
  ) {
    throw new Error("Checkout endpoint did not return a Stripe test-mode Payment Link");
  }

  console.log(
    JSON.stringify(
      {
        phase: "checkout-created",
        signup_id: checkout.signup_id,
        email,
        plan_code: checkout.plan_code,
        trial_days: checkout.trial_days,
      },
      null,
      2,
    ),
  );

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  try {
    await page.goto(checkout.checkout_url, {
      waitUntil: "domcontentloaded",
      timeout: 90_000,
    });

    await fillAny(
      page,
      [
        'input[type="email"]',
        'input[name="email"]',
        'input[autocomplete="email"]',
      ],
      email,
      { optional: true },
    );

    await fillAny(
      page,
      [
        'input[autocomplete="cc-number"]',
        'input[name="cardNumber"]',
        'input[name*="cardnumber" i]',
        'input[placeholder*="1234"]',
      ],
      "4242424242424242",
    );
    await fillAny(
      page,
      [
        'input[autocomplete="cc-exp"]',
        'input[name="cardExpiry"]',
        'input[name*="expiry" i]',
        'input[placeholder*="MM"]',
      ],
      "1234",
    );
    await fillAny(
      page,
      [
        'input[autocomplete="cc-csc"]',
        'input[name="cardCvc"]',
        'input[name*="cvc" i]',
        'input[placeholder*="CVC" i]',
      ],
      "123",
    );

    await fillAny(
      page,
      [
        'input[autocomplete="cc-name"]',
        'input[name="billingName"]',
        'input[name*="name" i]',
      ],
      "TerraSatch Acceptance",
      { optional: true },
    );
    await fillAny(
      page,
      [
        'input[autocomplete="postal-code"]',
        'input[name="billingPostalCode"]',
        'input[name*="postal" i]',
        'input[placeholder*="ZIP" i]',
      ],
      "84101",
      { optional: true },
    );

    await clickSubmit(page);

    await page.waitForURL(
      (url) =>
        url.hostname === "staging-api.terrasatch.com" &&
        url.pathname === "/api/v1/workspace/billing/success" &&
        Boolean(url.searchParams.get("session_id")),
      { timeout: 120_000 },
    );

    const redirected = new URL(page.url());
    const sessionId = redirected.searchParams.get("session_id");
    if (!sessionId) throw new Error("Stripe redirect did not include session_id");

    console.log(
      JSON.stringify(
        {
          phase: "stripe-checkout-complete",
          signup_id: checkout.signup_id,
          session_id: sessionId,
          email,
        },
        null,
        2,
      ),
    );

    let statusPayload = null;
    for (let attempt = 0; attempt < 80; attempt += 1) {
      try {
        const { data } = await fetchJson(
          `${BASE}/api/v1/workspace/billing/checkout/status?session_id=${encodeURIComponent(sessionId)}`,
        );
        statusPayload = data;
        if (
          data.state === "ready" &&
          data.subscription_status === "trialing" &&
          data.service_access === "full" &&
          data.activation_required === true
        ) {
          break;
        }
      } catch (error) {
        if (attempt > 10) console.log(`status retry: ${error.message}`);
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }

    if (
      !statusPayload ||
      statusPayload.state !== "ready" ||
      statusPayload.subscription_status !== "trialing" ||
      statusPayload.service_access !== "full" ||
      statusPayload.activation_required !== true
    ) {
      throw new Error(
        `Webhook-driven subscription state never became ready/trialing/full: ${JSON.stringify(statusPayload)}`,
      );
    }

    const { data: activation } = await fetchJson(
      `${BASE}/api/v1/workspace/billing/checkout/activation?session_id=${encodeURIComponent(sessionId)}`,
    );
    if (typeof activation.token !== "string" || activation.token.length < 32) {
      throw new Error("Staging activation token was not available after provisioning");
    }

    const { data: activated } = await fetchJson(
      `${BASE}/api/v1/workspace/billing/activate`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ token: activation.token, password }),
      },
    );

    if (activated.activated !== true || !activated.organization_id) {
      throw new Error(`Activation failed: ${JSON.stringify(activated)}`);
    }

    const { data: statusAfterActivation } = await fetchJson(
      `${BASE}/api/v1/workspace/billing/checkout/status?session_id=${encodeURIComponent(sessionId)}`,
    );

    if (
      statusAfterActivation.state !== "ready" ||
      statusAfterActivation.subscription_status !== "trialing" ||
      statusAfterActivation.service_access !== "full" ||
      statusAfterActivation.activation_required !== false
    ) {
      throw new Error(
        `Post-activation state is wrong: ${JSON.stringify(statusAfterActivation)}`,
      );
    }

    const anonymousSessionResponse = await context.request.get(
      `${BASE}/api/v1/workspace/session`,
    );
    if (!anonymousSessionResponse.ok()) {
      throw new Error(
        `Unable to initialize workspace session: HTTP ${anonymousSessionResponse.status()}`,
      );
    }
    const anonymousSession = await anonymousSessionResponse.json();
    if (
      anonymousSession.user !== null ||
      typeof anonymousSession.csrf_token !== "string" ||
      anonymousSession.csrf_token.length < 16
    ) {
      throw new Error(
        `Anonymous workspace session is invalid: ${JSON.stringify(anonymousSession)}`,
      );
    }

    const loginResponse = await context.request.post(
      `${BASE}/api/v1/workspace/login`,
      {
        headers: {
          "content-type": "application/json",
          "X-CSRF-Token": anonymousSession.csrf_token,
        },
        data: { email, password },
      },
    );
    if (!loginResponse.ok()) {
      throw new Error(
        `Workspace login failed: HTTP ${loginResponse.status()} ${await loginResponse.text()}`,
      );
    }
    const loginPayload = await loginResponse.json();
    if (
      typeof loginPayload.csrf_token !== "string" ||
      loginPayload.csrf_token.length < 16
    ) {
      throw new Error("Workspace login did not rotate and return a CSRF token");
    }

    const authenticatedSessionResponse = await context.request.get(
      `${BASE}/api/v1/workspace/session`,
    );
    if (!authenticatedSessionResponse.ok()) {
      throw new Error(
        `Authenticated workspace session failed: HTTP ${authenticatedSessionResponse.status()}`,
      );
    }
    const authenticatedSession = await authenticatedSessionResponse.json();
    const organization = Array.isArray(authenticatedSession.organizations)
      ? authenticatedSession.organizations.find(
          (item) => item.id === activated.organization_id,
        )
      : null;
    if (
      authenticatedSession.user?.email !== email ||
      !organization ||
      organization.role !== "owner"
    ) {
      throw new Error(
        `Authenticated workspace identity is wrong: ${JSON.stringify(authenticatedSession)}`,
      );
    }

    const organizationResponse = await context.request.get(
      `${BASE}/api/v1/workspace/organizations/${encodeURIComponent(activated.organization_id)}`,
    );
    if (!organizationResponse.ok()) {
      throw new Error(
        `Authenticated organization access failed: HTTP ${organizationResponse.status()}`,
      );
    }

    const portalResponse = await page.goto(`${BASE}/portal`, {
      waitUntil: "domcontentloaded",
      timeout: 90_000,
    });
    if (!portalResponse || !portalResponse.ok()) {
      throw new Error(
        `Field Workspace portal handoff failed: HTTP ${portalResponse?.status() ?? "unknown"}`,
      );
    }
    if (!(await page.getByText("FIELD WORKSPACE", { exact: false }).first().isVisible())) {
      throw new Error("Field Workspace portal did not render after authenticated handoff");
    }

    const logoutResponse = await context.request.post(
      `${BASE}/api/v1/workspace/logout`,
      {
        headers: {
          "X-CSRF-Token": authenticatedSession.csrf_token || loginPayload.csrf_token,
        },
      },
    );
    if (!logoutResponse.ok()) {
      throw new Error(
        `Workspace logout failed: HTTP ${logoutResponse.status()} ${await logoutResponse.text()}`,
      );
    }

    const loggedOutSessionResponse = await context.request.get(
      `${BASE}/api/v1/workspace/session`,
    );
    const loggedOutSession = await loggedOutSessionResponse.json();
    if (!loggedOutSessionResponse.ok() || loggedOutSession.user !== null) {
      throw new Error(
        `Workspace logout did not clear authentication: ${JSON.stringify(loggedOutSession)}`,
      );
    }

    console.log(
      JSON.stringify(
        {
          ok: true,
          phase: "accepted",
          signup_id: checkout.signup_id,
          session_id: sessionId,
          organization_id: activated.organization_id,
          email,
          subscription_status: statusAfterActivation.subscription_status,
          service_access: statusAfterActivation.service_access,
          activation_required: statusAfterActivation.activation_required,
          workspace_login: "passed",
          workspace_organization_access: "passed",
          portal_handoff: "passed",
          workspace_logout: "passed",
        },
        null,
        2,
      ),
    );
  } catch (error) {
    await page.screenshot({
      path: "billing-staging-acceptance-failure.png",
      fullPage: true,
    }).catch(() => {});
    fail(error instanceof Error ? error.message : String(error), {
      page_url: page.url(),
      page_title: await page.title().catch(() => ""),
    });
  } finally {
    await browser.close();
  }
}

await main();
