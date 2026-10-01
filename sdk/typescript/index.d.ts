// OpenAPI-backed TerraSatch SDK declarations.
// Regenerate from the canonical FastAPI contract with scripts/generate-typescript-sdk.py.

export type ActiveMapContext = {
  map_id?: string | null;
  center_latitude?: number | null;
  center_longitude?: number | null;
  zoom?: number | null;
  selected_layers?: string[];
  selected_terrain?: string | null;
};

export type Chat = {
  request_id?: string | null;
  message: string;
  site_id?: string | null;
  transmission_id?: string | null;
  objective?: string | null;
  active_map?: ActiveMapContext | null;
};

export type Observation = {
  site_id: string;
  request_id: string;
  text: string;
  latitude?: number | null;
  longitude?: number | null;
};

export type DiscoveryPhaseUpdate = {
  listen?: "off" | "active" | "testing" | "ready" | null;
  watch?: "off" | "active" | "testing" | "ready" | null;
  learn?: "off" | "active" | "testing" | "ready" | null;
  adapt?: "off" | "active" | "testing" | "ready" | null;
};

export type DiscoveryWorkflowCountUpdate = {
  identified?: number | null;
  testing?: number | null;
  approved?: number | null;
};

export type DiscoveryStateUpdate = {
  status?: "not_started" | "active" | "complete" | "integrated" | null;
  day?: number | null;
  phases?: DiscoveryPhaseUpdate | null;
  workflow_counts?: DiscoveryWorkflowCountUpdate | null;
};

export type WorkspaceConvergenceUpdate = {
  operational_domain?: string | null;
  workspace_template?: string | null;
  runtime_mode?: "legacy" | "shadow" | "agent_read" | "agent_propose" | null;
  recommended_modules?: string[] | null;
  preferred_map_layers?: string[] | null;
  workflow_preferences?: string[] | null;
  discovery?: DiscoveryStateUpdate | null;
};

export type WorkspaceDiscoveryPhases = {
  listen: "off" | "active" | "testing" | "ready";
  watch: "off" | "active" | "testing" | "ready";
  learn: "off" | "active" | "testing" | "ready";
  adapt: "off" | "active" | "testing" | "ready";
};

export type WorkspaceDiscoveryWorkflowCounts = {
  identified: number;
  testing: number;
  approved: number;
};

export type WorkspaceDiscoveryState = {
  status: "not_started" | "active" | "complete" | "integrated";
  duration_days: number;
  day: number;
  phases: WorkspaceDiscoveryPhases;
  workflow_counts: WorkspaceDiscoveryWorkflowCounts;
};

export type WorkspaceProfileResponse = {
  operational_domain: string;
  workspace_template: string;
  runtime_mode: "legacy" | "shadow" | "agent_read" | "agent_propose";
  recommended_modules: string[];
  preferred_map_layers: string[];
  workflow_preferences: string[];
  discovery_state: WorkspaceDiscoveryState;
};

export type WorkspaceEdgeCapabilityDevice = {
  id: string;
  site_id: string;
  name: string;
  agent_version?: string | null;
  capabilities: string[];
  last_seen_at?: string | null;
};

export type WorkspaceCapabilityPolicy = {
  agent_reads_enabled: boolean;
  agent_proposals_enabled: boolean;
  shadow_only: boolean;
  consequential_actions_require_approval: boolean;
  physical_actions_require_approval: boolean;
};

export type WorkspaceCapabilityManifest = {
  runtime_mode: "legacy" | "shadow" | "agent_read" | "agent_propose";
  read: string[];
  write: string[];
  edge: string[];
  physical: string[];
  connected_providers: string[];
  edge_devices: WorkspaceEdgeCapabilityDevice[];
  policy: WorkspaceCapabilityPolicy;
};

export type WorkspaceConvergenceResponse = {
  profile: WorkspaceProfileResponse;
  capability_manifest: WorkspaceCapabilityManifest;
};

export type WorkspaceConvergenceUpdateResponse = {
  profile: WorkspaceProfileResponse;
};

export type WorkspaceOrganizationSummary = {
  id: string;
  name: string;
  role: string;
};

export type WorkspaceUserSummary = {
  id: string;
  name: string;
  email: string;
};

export type WorkspaceSessionResponse = {
  user: WorkspaceUserSummary | null;
  organizations: WorkspaceOrganizationSummary[];
  csrf_token: string;
};

export type WorkspaceLoginResponse = {
  csrf_token: string;
};

export type WorkspaceLogoutResponse = {
  signed_out: boolean;
};

export type EntitlementsResponse = {
  max_sites: number | null;
  max_members: number | null;
  max_edge_devices: number | null;
  max_channels: number | null;
  included_processing_hours: number | null;
  retention_days: number | null;
  api_access: boolean;
  priority_support: boolean;
};

export type SubscriptionResponse = {
  organization_id: string;
  managed: boolean;
  plan_code: "field" | "team" | "operations" | "enterprise" | null;
  billing_interval: "monthly" | "annual" | null;
  status: string;
  service_access: "full" | "grace" | "restricted" | "legacy";
  trial_ends_at: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  grace_ends_at: string | null;
  entitlements: EntitlementsResponse | null;
};

export type WorkspaceDeviceSummary = {
  id: string;
  name: string;
  enabled: boolean;
  last_seen_at?: string | null;
  agent_version?: string | null;
};

export type WorkspaceEngineSummary = {
  provider: string;
  model: string;
};

export type WorkspaceIntegrationsResponse = {
  devices: WorkspaceDeviceSummary[];
  engine: WorkspaceEngineSummary;
  catalog: Record<string, unknown>[];
  connections: Record<string, unknown>[];
};

export type WorkspaceSiteSummary = {
  id: string;
  name: string;
};

export type WorkspaceTeamSummary = {
  id: string;
  name: string;
  site_id?: string | null;
};

export type WorkspaceFieldAssetResponse = {
  id: string;
  site_id?: string | null;
  team_id?: string | null;
  owner_user_id?: string | null;
  controller_edge_device_id?: string | null;
  name: string;
  type: string;
  provider: string;
  capabilities: string[];
  state: string;
  location: Record<string, unknown>;
  policy: Record<string, unknown>;
  enabled: boolean;
};

export type WorkspaceRecordInterpretation = {
  id: string;
  summary: string;
  type: string;
  latitude?: number | null;
  longitude?: number | null;
  location?: string | null;
  confidence: number;
  spatial_status?: string | null;
};

export type WorkspaceRecordResponse = {
  id: string;
  source: string;
  speaker?: string | null;
  timestamp: string;
  original?: string | null;
  location?: unknown | null;
  interpretations: WorkspaceRecordInterpretation[];
};

export type WorkspaceActionResponse = {
  id: string;
  source_id?: string | null;
  type: string;
  reason: string;
  message?: string | null;
  status: string;
  integration_execution: Record<string, unknown>;
};

export type WorkspaceMessageResponse = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

export type WorkspaceSnapshotResponse = {
  role: string;
  modules: string[];
  satchy_preferences: Record<string, unknown>;
  convergence: WorkspaceConvergenceResponse;
  integrations: WorkspaceIntegrationsResponse;
  subscription: SubscriptionResponse;
  sites: WorkspaceSiteSummary[];
  teams: WorkspaceTeamSummary[];
  assets: WorkspaceFieldAssetResponse[];
  records: WorkspaceRecordResponse[];
  actions: WorkspaceActionResponse[];
  messages: WorkspaceMessageResponse[];
};

export type SatchyRunStepResponse = {
  id: string;
  sequence: number;
  type: string;
  status: string;
  label: string;
  detail: Record<string, unknown>;
  source_refs: Record<string, unknown>[];
  action_id?: string | null;
  created_at: string;
  completed_at?: string | null;
};

export type SatchyRunResponse = {
  id: string;
  request_id: string;
  organization_id: string;
  site_id: string;
  user_id?: string | null;
  objective?: string | null;
  input_text: string;
  response_text?: string | null;
  model?: string | null;
  status: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
  steps: SatchyRunStepResponse[];
};

export type SatchyChatResponse = {
  answer: string;
  action_id?: string | null;
  action_status?: string | null;
  approval_required: boolean;
  run_id: string;
  run_status: string;
};

export type WorkspaceActionReviewResponse = {
  id: string;
  status: string;
  integration_detail?: unknown | null;
  integration_execution: Record<string, unknown>;
};

export type WorkspaceObservationResponse = {
  id: string;
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
  loginWorkspace(email: string, password: string, csrfToken: string): Promise<WorkspaceLoginResponse>;
  logoutWorkspace(csrfToken: string): Promise<WorkspaceLogoutResponse>;
  getWorkspace(organizationId: string): Promise<WorkspaceSnapshotResponse>;
  getWorkspaceConvergence(organizationId: string): Promise<WorkspaceConvergenceResponse>;
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
  listSatchyRuns(organizationId: string, limit?: number): Promise<SatchyRunResponse[]>;
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
  connectEvents(options?: {
    token?: string;
    topics?: RealtimeTopic[];
  }): WebSocket;
}
