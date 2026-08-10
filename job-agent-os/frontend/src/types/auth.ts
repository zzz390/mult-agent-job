/** Auth types (matches backend schemas/auth.py) */

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
  phone?: string | null;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  user_id: string;
  username: string;
  access_token: string;
  refresh_token: string;
  expires_in: number;
  token_type: string;
}
