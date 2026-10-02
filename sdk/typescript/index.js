const DEFAULT_API_ORIGIN = "https://api.terrasatch.com";

function stripTrailingSlash(value) {
  return value.replace(/\/$/, "");
}

function encode(value) {
  return encodeURIComponent(String(value));
}

function defaultBaseUrl() {
  if (typeof window !== "undefined" && window.location?.origin) {
    return window.location.origin;
  }
  return DEFAULT_API_ORIGIN;
}

function deriveWebSocketBaseUrl(baseUrl) {
  return stripTrailingSlash(baseUrl)
    .replace(/^https:/, "wss:")
    .replace(/^http:/, "ws:");
}

export class TerraSatchApiError extends Error {
  constructor(status, message, detail = undefined) {
    super(message);
    this.name = "TerraSatchApiError";
    this.status = status;
    this.detail = detail;
  }
}

export class TerraSatchClient {
  constructor(options = {}) {
    this.baseUrl = stripTrailingSlash(options.baseUrl || defaultBaseUrl());
    this.wsBaseUrl = stripTrailingSlash(
      options.wsBaseUrl || deriveWebSocketBaseUrl(this.baseUrl),
    );
    this.token = options.token || null;
    this.credentials = options.credentials || "include";
    this.fetchImpl =
      options.fetch ||
      (typeof globalThis.fetch === "function"
        ? globalThis.fetch.bind(globalThis)
        : undefined);
    this.resolveUrl =
      options.resolveUrl || ((path) => `${this.baseUrl}${path}`);
    this.WebSocketImpl = options.WebSocket || globalThis.WebSocket;

    if (typeof this.fetchImpl !== "function") {
      throw new Error("TerraSatchClient requires a fetch implementation");
    }
  }

  async request(path, init = {}) {
    const { csrfToken, ...requestInit } = init;
    const headers = new Headers(requestInit.headers || {});
    headers.set("accept", "application/json");
    if (requestInit.body && !headers.has("content-type")) {
      headers.set("content-type", "application/json");
    }
    if (csrfToken) {
      headers.set("x-csrf-token", csrfToken);
    }
    if (this.token && !headers.has("authorization")) {
      headers.set("authorization", `Bearer ${this.token}`);
    }

    const response = await this.fetchImpl(this.resolveUrl(path), {
      ...requestInit,
      headers,
      credentials: this.credentials,
      cache: requestInit.cache || "no-store",
    });

    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json")
      ? await response.json()
      : { detail: await response.text() };

    if (!response.ok) {
      const message =
        typeof payload?.detail === "string"
          ? payload.detail
          : `TerraSatch API request failed with status ${response.status}`;
      throw new TerraSatchApiError(response.status, message, payload);
    }
    return payload;
  }

  workspaceSession() {
    return this.request("/api/v1/workspace/session");
  }

  loginWorkspace(email, password, csrfToken) {
    return this.request("/api/v1/workspace/login", {
      method: "POST",
      csrfToken,
      body: JSON.stringify({ email, password }),
    });
  }

  logoutWorkspace(csrfToken) {
    return this.request("/api/v1/workspace/logout", {
      method: "POST",
      csrfToken,
      body: JSON.stringify({}),
    });
  }

  getWorkspace(organizationId) {
    return this.request(
      `/api/v1/workspace/organizations/${encode(organizationId)}`,
    );
  }

  getWorkspaceConvergence(organizationId) {
    return this.request(
      `/api/v1/workspace/organizations/${encode(organizationId)}/convergence`,
    );
  }

  updateWorkspaceConvergence(organizationId, payload, csrfToken) {
    return this.request(
      `/api/v1/workspace/organizations/${encode(organizationId)}/convergence`,
      {
        method: "PATCH",
        csrfToken,
        body: JSON.stringify(payload),
      },
    );
  }

  chatWithSatchy(organizationId, payload, csrfToken) {
    return this.request(
      `/api/v1/workspace/organizations/${encode(organizationId)}/chat`,
      {
        method: "POST",
        csrfToken,
        body: JSON.stringify(payload),
      },
    );
  }

  listSatchyRuns(organizationId, limit = 20) {
    const safeLimit = Math.max(1, Math.min(50, Number(limit) || 20));
    return this.request(
      `/api/v1/workspace/organizations/${encode(organizationId)}/runs?limit=${safeLimit}`,
    );
  }

  getSatchyRun(organizationId, runId) {
    return this.request(
      `/api/v1/workspace/organizations/${encode(organizationId)}/runs/${encode(runId)}`,
    );
  }

  reviewSatchyAction(
    organizationId,
    actionId,
    decision,
    csrfToken,
    notes = "",
  ) {
    return this.request(
      `/api/v1/workspace/organizations/${encode(organizationId)}/actions/${encode(actionId)}`,
      {
        method: "POST",
        csrfToken,
        body: JSON.stringify({ decision, notes }),
      },
    );
  }

  createWorkspaceObservation(organizationId, payload, csrfToken) {
    return this.request(
      `/api/v1/workspace/organizations/${encode(organizationId)}/observations`,
      {
        method: "POST",
        csrfToken,
        body: JSON.stringify(payload),
      },
    );
  }

  getWorkspaceIntegrationCatalog(organizationId) {
    return this.request(
      `/api/v1/workspace/organizations/${encode(organizationId)}/integrations/catalog`,
    );
  }

  createWorkspaceIntegration(organizationId, payload, csrfToken) {
    return this.request(
      `/api/v1/workspace/organizations/${encode(organizationId)}/integrations`,
      {
        method: "POST",
        csrfToken,
        body: JSON.stringify(payload),
      },
    );
  }

  configureWorkspaceIntegrationCredentials(
    organizationId,
    connectionId,
    values,
    csrfToken,
  ) {
    return this.request(
      `/api/v1/workspace/organizations/${encode(organizationId)}/integrations/${encode(connectionId)}/credentials`,
      {
        method: "POST",
        csrfToken,
        body: JSON.stringify({ values }),
      },
    );
  }

  authorizeWorkspaceIntegration(organizationId, connectionId, csrfToken) {
    return this.request(
      `/api/v1/workspace/organizations/${encode(organizationId)}/integrations/${encode(connectionId)}/authorize`,
      {
        method: "POST",
        csrfToken,
        body: "{}",
      },
    );
  }

  testWorkspaceIntegration(organizationId, connectionId, csrfToken) {
    return this.request(
      `/api/v1/workspace/organizations/${encode(organizationId)}/integrations/${encode(connectionId)}/test`,
      {
        method: "POST",
        csrfToken,
        body: "{}",
      },
    );
  }

  revokeWorkspaceIntegration(organizationId, connectionId, csrfToken) {
    return this.request(
      `/api/v1/workspace/organizations/${encode(organizationId)}/integrations/${encode(connectionId)}/revoke`,
      {
        method: "POST",
        csrfToken,
        body: "{}",
      },
    );
  }

  queryWorkspaceIntegration(organizationId, payload, csrfToken) {
    return this.request(
      `/api/v1/workspace/organizations/${encode(organizationId)}/integrations/query`,
      {
        method: "POST",
        csrfToken,
        body: JSON.stringify(payload),
      },
    );
  }

  connectEvents({ token = this.token, topics = ["events"] } = {}) {
    if (!token) {
      throw new Error("TerraSatch realtime subscriptions require an API token");
    }
    if (typeof this.WebSocketImpl !== "function") {
      throw new Error("TerraSatchClient requires a WebSocket implementation");
    }

    const socket = new this.WebSocketImpl(`${this.wsBaseUrl}/ws/v1/events`);
    socket.addEventListener("open", () => {
      socket.send(
        JSON.stringify({
          action: "subscribe",
          token,
          topics,
        }),
      );
    });
    return socket;
  }
}
