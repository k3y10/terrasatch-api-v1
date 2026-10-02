// AUTO-GENERATED FROM TERRASATCH OPENAPI. DO NOT EDIT BY HAND.
// schema-sha256: 147d500106a5f9c13544f8f41190b9ec5bbfe09a3a732bf7aac370255ae95d1e

export type ActiveMapContext = {
  center_latitude?: number | null;
  center_longitude?: number | null;
  map_id?: string | null;
  selected_layers?: string[];
  selected_terrain?: string | null;
  zoom?: number | null;
};

export type BillingInterval = "monthly" | "annual";

export type Chat = {
  active_map?: ActiveMapContext | null;
  message: string;
  objective?: string | null;
  request_id?: string | null;
  site_id?: string | null;
  transmission_id?: string | null;
};

export type DiscoveryPhaseUpdate = {
  adapt?: "off" | "active" | "testing" | "ready" | null;
  learn?: "off" | "active" | "testing" | "ready" | null;
  listen?: "off" | "active" | "testing" | "ready" | null;
  watch?: "off" | "active" | "testing" | "ready" | null;
};

export type DiscoveryStateUpdate = {
  day?: number | null;
  phases?: DiscoveryPhaseUpdate | null;
  status?: "not_started" | "active" | "complete" | "integrated" | null;
  workflow_counts?: DiscoveryWorkflowCountUpdate | null;
};

export type DiscoveryWorkflowCountUpdate = {
  approved?: number | null;
  identified?: number | null;
  testing?: number | null;
};

export type EntitlementsResponse = {
  api_access: boolean;
  included_processing_hours: number | null;
  max_channels: number | null;
  max_edge_devices: number | null;
  max_members: number | null;
  max_sites: number | null;
  priority_support: boolean;
  retention_days: number | null;
};

export type Observation = {
  latitude?: number | null;
  longitude?: number | null;
  request_id: string;
  site_id: string;
  text: string;
};

export type PlanCode = "field" | "team" | "operations" | "enterprise";

export type SatchyChatResponse = {
  action_id: string | null;
  action_status: string | null;
  answer: string;
  approval_required: boolean;
  run_id: string;
  run_status: string;
};

export type SatchyRunResponse = {
  completed_at: string | null;
  created_at: string;
  id: string;
  input_text: string;
  metadata: Record<string, unknown>;
  model: string | null;
  objective: string | null;
  organization_id: string;
  request_id: string;
  response_text: string | null;
  site_id: string;
  status: string;
  steps: SatchyRunStepResponse[];
  updated_at: string;
  user_id: string | null;
};

export type SatchyRunStepResponse = {
  action_id: string | null;
  completed_at: string | null;
  created_at: string;
  detail: Record<string, unknown>;
  id: string;
  label: string;
  sequence: number;
  source_refs: Record<string, unknown>[];
  status: string;
  type: string;
};

export type SubscriptionResponse = {
  billing_interval: BillingInterval | null;
  cancel_at_period_end: boolean;
  current_period_end: string | null;
  entitlements: EntitlementsResponse | null;
  grace_ends_at: string | null;
  managed: boolean;
  organization_id: string;
  plan_code: PlanCode | null;
  service_access: "full" | "grace" | "restricted" | "legacy";
  status: string;
  trial_ends_at: string | null;
};

export type WorkspaceActionResponse = {
  id: string;
  integration_execution: Record<string, unknown>;
  message: string | null;
  reason: string;
  source_id: string | null;
  status: string;
  type: string;
};

export type WorkspaceActionReviewResponse = {
  id: string;
  integration_detail: unknown | null;
  integration_execution: Record<string, unknown>;
  status: string;
};

export type WorkspaceCapabilityManifest = {
  connected_providers: string[];
  edge: string[];
  edge_devices: WorkspaceEdgeCapabilityDevice[];
  physical: string[];
  policy: WorkspaceCapabilityPolicy;
  read: string[];
  runtime_mode: "legacy" | "shadow" | "agent_read" | "agent_propose";
  write: string[];
};

export type WorkspaceCapabilityPolicy = {
  agent_proposals_enabled: boolean;
  agent_reads_enabled: boolean;
  consequential_actions_require_approval: boolean;
  physical_actions_require_approval: boolean;
  shadow_only: boolean;
};

export type WorkspaceCapabilityResponse = {
  access: "read" | "write";
  key: string;
  label: string;
};

export type WorkspaceConvergenceResponse = {
  capability_manifest: WorkspaceCapabilityManifest;
  profile: WorkspaceProfileResponse;
};

export type WorkspaceConvergenceUpdate = {
  discovery?: DiscoveryStateUpdate | null;
  operational_domain?: string | null;
  preferred_map_layers?: string[] | null;
  recommended_modules?: string[] | null;
  runtime_mode?: "legacy" | "shadow" | "agent_read" | "agent_propose" | null;
  workflow_preferences?: string[] | null;
  workspace_template?: string | null;
};

export type WorkspaceConvergenceUpdateResponse = {
  profile: WorkspaceProfileResponse;
};

export type WorkspaceDeviceSummary = {
  agent_version: string | null;
  enabled: boolean;
  id: string;
  last_seen_at: string | null;
  name: string;
};

export type WorkspaceDiscoveryPhases = {
  adapt: "off" | "active" | "testing" | "ready";
  learn: "off" | "active" | "testing" | "ready";
  listen: "off" | "active" | "testing" | "ready";
  watch: "off" | "active" | "testing" | "ready";
};

export type WorkspaceDiscoveryState = {
  day: number;
  duration_days: number;
  phases: WorkspaceDiscoveryPhases;
  status: "not_started" | "active" | "complete" | "integrated";
  workflow_counts: WorkspaceDiscoveryWorkflowCounts;
};

export type WorkspaceDiscoveryWorkflowCounts = {
  approved: number;
  identified: number;
  testing: number;
};

export type WorkspaceEdgeCapabilityDevice = {
  agent_version: string | null;
  capabilities: string[];
  id: string;
  last_seen_at: string | null;
  name: string;
  site_id: string;
};

export type WorkspaceEngineSummary = {
  model: string;
  provider: string;
};

export type WorkspaceFieldAssetResponse = {
  capabilities: string[];
  controller_edge_device_id: string | null;
  enabled: boolean;
  id: string;
  location: Record<string, unknown>;
  name: string;
  owner_user_id: string | null;
  policy: Record<string, unknown>;
  provider: string;
  site_id: string | null;
  state: string;
  team_id: string | null;
  type: string;
};

export type WorkspaceIntegrationCatalogItem = {
  allowed: boolean;
  allowed_scopes: string[];
  auth: string;
  can_connect: boolean;
  capabilities: string[];
  capability_details: WorkspaceCapabilityResponse[];
  category: string;
  connect_status: "managed" | "available" | "external_setup_required" | "needs_configuration" | "partner_required" | "coming_soon";
  connected: boolean;
  connected_scopes: string[];
  description: string;
  key: string;
  name: string;
  requires_admin: boolean;
  runtime_ready: boolean;
  scopes: string[];
  setup_status: "managed" | "planned" | "available";
  support_status: "managed" | "supported" | "partner_required" | "coming_soon";
};

export type WorkspaceIntegrationSetupField = {
  key: string;
  required: boolean;
  type?: "string" | "number" | "list";
};

export type WorkspaceIntegrationSetupGuidance = {
  detail: string;
  configuration_fields: WorkspaceIntegrationSetupField[];
  credential_fields: WorkspaceIntegrationSetupField[];
};

export type WorkspaceIntegrationConnection = {
  can_manage?: boolean;
  configuration: Record<string, unknown>;
  created_at: string;
  display_name: string;
  enabled: boolean;
  id: string;
  last_error: string | null;
  last_synced_at: string | null;
  owner_user_id: string | null;
  provider: string;
  provider_account_id: string | null;
  provider_account_label: string | null;
  provider_name: string;
  scope: string;
  status: string;
  team_id: string | null;
};

export type WorkspaceIntegrationSetupCatalogItem =
  WorkspaceIntegrationCatalogItem & {
    connections: WorkspaceIntegrationConnection[];
    setup: WorkspaceIntegrationSetupGuidance;
  };

export type WorkspaceIntegrationsResponse = {
  catalog: WorkspaceIntegrationCatalogItem[];
  connections: Record<string, unknown>[];
  devices: WorkspaceDeviceSummary[];
  engine: WorkspaceEngineSummary;
};

export type WorkspaceIntegrationCreateRequest = {
  provider: string;
  scope: "user" | "team" | "organization";
  team_id?: string | null;
  display_name?: string | null;
  configuration?: Record<string, unknown>;
};

export type WorkspaceIntegrationAuthorizeResponse = {
  connection: WorkspaceIntegrationConnection;
  expires_at: string;
  url: string;
};

export type WorkspaceIntegrationQueryRequest = {
  capability:
    | "map.features.query"
    | "map.style.read"
    | "data.query"
    | "weather.forecast.read";
  connection_id?: string | null;
  workflow_key?: string | null;
  payload?: Record<string, unknown>;
};

export type WorkspaceLoginResponse = {
  csrf_token: string;
};

export type WorkspaceLogoutResponse = {
  signed_out: boolean;
};

export type WorkspaceMessageResponse = {
  content: string;
  id: string;
  role: "user" | "assistant";
};

export type WorkspaceObservationResponse = {
  id: string;
};

export type WorkspaceOrganizationSummary = {
  id: string;
  name: string;
  role: string;
};

export type WorkspaceProfileResponse = {
  discovery_state: WorkspaceDiscoveryState;
  operational_domain: string;
  preferred_map_layers: string[];
  recommended_modules: string[];
  runtime_mode: "legacy" | "shadow" | "agent_read" | "agent_propose";
  workflow_preferences: string[];
  workspace_template: string;
};

export type WorkspaceRecordInterpretation = {
  confidence: number;
  id: string;
  latitude: number | null;
  location: string | null;
  longitude: number | null;
  spatial_status: string | null;
  summary: string;
  type: string;
};

export type WorkspaceRecordResponse = {
  id: string;
  interpretations: WorkspaceRecordInterpretation[];
  location: unknown | null;
  original: string | null;
  source: string;
  speaker: string | null;
  timestamp: string;
};

export type WorkspaceSessionResponse = {
  csrf_token: string;
  organizations: WorkspaceOrganizationSummary[];
  user: WorkspaceUserSummary | null;
};

export type WorkspaceSiteSummary = {
  id: string;
  name: string;
};

export type WorkspaceSnapshotResponse = {
  actions: WorkspaceActionResponse[];
  assets: WorkspaceFieldAssetResponse[];
  convergence: WorkspaceConvergenceResponse;
  integrations: WorkspaceIntegrationsResponse;
  messages: WorkspaceMessageResponse[];
  modules: string[];
  records: WorkspaceRecordResponse[];
  role: string;
  satchy_preferences: Record<string, unknown>;
  sites: WorkspaceSiteSummary[];
  subscription: SubscriptionResponse;
  teams: WorkspaceTeamSummary[];
};

export type WorkspaceTeamSummary = {
  id: string;
  name: string;
  site_id: string | null;
};

export type WorkspaceUserSummary = {
  email: string;
  id: string;
  name: string;
};

export type RealtimeTopic = "events" | "transmissions" | "transcripts";

export type TerraSatchClientOptions = {
  baseUrl?: string;
  wsBaseUrl?: string;
  token?: string;
  credentials?: RequestCredentials;
  fetch?: typeof fetch;
  resolveUrl?: (path: string) => string;
  WebSocket?: typeof WebSocket;
};

export type TerraSatchRequestOptions = RequestInit & {
  csrfToken?: string;
};

export class TerraSatchApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown);
}

export class TerraSatchClient {
  constructor(options?: TerraSatchClientOptions);
  request<T>(path: string, init?: TerraSatchRequestOptions): Promise<T>;
  workspaceSession(): Promise<WorkspaceSessionResponse>;
  loginWorkspace(
    email: string, password: string, csrfToken: string
  ): Promise<WorkspaceLoginResponse>;
  logoutWorkspace(csrfToken: string): Promise<WorkspaceLogoutResponse>;
  getWorkspace(organizationId: string): Promise<WorkspaceSnapshotResponse>;
  getWorkspaceConvergence(
    organizationId: string
  ): Promise<WorkspaceConvergenceResponse>;
  updateWorkspaceConvergence(
    organizationId: string,
    payload: WorkspaceConvergenceUpdate,
    csrfToken: string,
  ): Promise<WorkspaceConvergenceUpdateResponse>;
  chatWithSatchy(
    organizationId: string,
    payload: Chat,
    csrfToken: string,
  ): Promise<SatchyChatResponse>;
  listSatchyRuns(
    organizationId: string, limit?: number
  ): Promise<SatchyRunResponse[]>;
  getSatchyRun(organizationId: string, runId: string): Promise<SatchyRunResponse>;
  reviewSatchyAction(
    organizationId: string,
    actionId: string,
    decision: "approve" | "reject",
    csrfToken: string,
    notes?: string,
  ): Promise<WorkspaceActionReviewResponse>;
  createWorkspaceObservation(
    organizationId: string,
    payload: Observation,
    csrfToken: string,
  ): Promise<WorkspaceObservationResponse>;
  getWorkspaceIntegrationCatalog(
    organizationId: string,
  ): Promise<WorkspaceIntegrationSetupCatalogItem[]>;
  createWorkspaceIntegration(
    organizationId: string,
    payload: WorkspaceIntegrationCreateRequest,
    csrfToken: string,
  ): Promise<WorkspaceIntegrationConnection>;
  configureWorkspaceIntegrationCredentials(
    organizationId: string,
    connectionId: string,
    values: Record<string, string>,
    csrfToken: string,
  ): Promise<WorkspaceIntegrationConnection>;
  authorizeWorkspaceIntegration(
    organizationId: string,
    connectionId: string,
    csrfToken: string,
  ): Promise<WorkspaceIntegrationAuthorizeResponse>;
  testWorkspaceIntegration(
    organizationId: string,
    connectionId: string,
    csrfToken: string,
  ): Promise<WorkspaceIntegrationConnection>;
  revokeWorkspaceIntegration(
    organizationId: string,
    connectionId: string,
    csrfToken: string,
  ): Promise<WorkspaceIntegrationConnection>;
  queryWorkspaceIntegration(
    organizationId: string,
    payload: WorkspaceIntegrationQueryRequest,
    csrfToken: string,
  ): Promise<Record<string, unknown>>;
  connectEvents(options?: {
    token?: string;
    topics?: RealtimeTopic[];
  }): WebSocket;
}
