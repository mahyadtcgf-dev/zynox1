export type RoleName = 'admin' | 'operator' | 'viewer';

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface PaginationParams {
  page?: number;
  page_size?: number;
  sort_by?: string | null;
  sort_order?: 'asc' | 'desc';
  search?: string | null;
}

export interface MessageOut {
  message: string;
  detail?: unknown;
}

export interface User {
  id: string;
  username: string;
  email: string;
  is_active: boolean;
  totp_enabled: boolean;
  last_login_at?: string | null;
  created_at: string;
  roles: string[];
  permissions: string[];
}

export interface TokenOut {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface RoleOut {
  id: string;
  name: string;
  description?: string | null;
  is_system: boolean;
  permissions: string[];
}

export type ProtocolType = 'vless' | 'vmess' | 'trojan';
export type TransportType = 'tcp' | 'ws' | 'xhttp';
export type SecurityType = 'none' | 'tls' | 'reality' | 'xtls';

export interface ServiceConfig {
  id: string;
  name: string;
  uuid: string;
  protocol: ProtocolType;
  transport: TransportType;
  service_id?: string | null;
  host: string;
  port: number;
  path?: string | null;
  sni?: string | null;
  host_header?: string | null;
  flow?: string | null;
  security: SecurityType;
  tls_server_name?: string | null;
  fingerprint?: string | null;
  alpn?: string | null;
  allow_insecure: boolean;
  extra?: Record<string, unknown> | null;
  metadata?: Record<string, unknown> | null;
  enabled: boolean;
  expires_at?: string | null;
  last_used_at?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConfigListItem {
  id: string;
  name: string;
  uuid: string;
  protocol: ProtocolType;
  transport: TransportType;
  host: string;
  share_url: string;
  enabled: boolean;
  expires_at?: string | null;
  created_at: string;
  service_id?: string | null;
}

export interface ConfigGenerated {
  config: ServiceConfig;
  share_url: string;
  xray: Record<string, unknown>;
  qr_code?: string | null;
}

export interface Service {
  id: string;
  name: string;
  description?: string | null;
  host: string;
  port: number;
  protocol: ProtocolType;
  transport: TransportType;
  tag?: string | null;
  status: string;
  enabled: boolean;
  server_id?: string | null;
  last_error?: string | null;
  config_count: number;
  created_at: string;
  updated_at: string;
}

export interface Server {
  id: string;
  name: string;
  address: string;
  location?: string | null;
  provider?: string | null;
  status: string;
  enabled: boolean;
  cpu_percent?: number | null;
  memory_percent?: number | null;
  disk_percent?: number | null;
  network_rx_bps?: number | null;
  network_tx_bps?: number | null;
  uptime_seconds?: number | null;
  notes?: string | null;
  service_count: number;
  created_at: string;
  updated_at: string;
}

export interface SystemMetrics {
  cpu_percent: number;
  memory_percent: number;
  memory_total_bytes: number;
  memory_used_bytes: number;
  disk_percent: number;
  disk_total_bytes: number;
  disk_used_bytes: number;
  network_rx_bps: number;
  network_tx_bps: number;
  uptime_seconds: number;
  load_average?: number[] | null;
  timestamp: string;
}

export interface AuditLog {
  id: string;
  actor_id?: string | null;
  actor_username?: string | null;
  actor_type: string;
  action: string;
  resource_type: string;
  resource_id?: string | null;
  details?: Record<string, unknown> | null;
  status: string;
  ip_address?: string | null;
  user_agent?: string | null;
  created_at: string;
}

export interface DashboardStats {
  app_name: string;
  services_total: number;
  services_active: number;
  services_offline: number;
  services_disabled: number;
  configs_total: number;
  configs_active: number;
  configs_expired: number;
  users_total: number;
  users_active: number;
  servers_total: number;
  servers_online: number;
  telegram_bot_configured: boolean;
  telegram_authorized_users: number;
  system?: SystemMetricsSummary | null;
  recent_activity: AuditLog[];
}

export interface SystemMetricsSummary {
  cpu_percent: number;
  memory_percent: number;
  disk_percent: number;
  network_rx_bps: number;
  network_tx_bps: number;
  uptime_seconds: number;
}

export interface TelegramUser {
  id: string;
  telegram_id: string;
  username?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  is_authorized: boolean;
  user_id?: string | null;
  linked_username?: string | null;
  linked_at?: string | null;
  last_seen_at?: string | null;
  created_at: string;
}

export interface TelegramStatus {
  bot_configured: boolean;
  bot_username?: string | null;
  mini_app_url?: string | null;
  authorized_users: number;
  webhook_url?: string | null;
  polling: boolean;
}

export interface SystemSetting {
  id: string;
  key: string;
  value?: string | null;
  description?: string | null;
  updated_at: string;
}
