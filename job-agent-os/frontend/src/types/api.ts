/** Unified API response types (matches backend response.py) */

export interface ApiMeta {
  request_id: string;
  timestamp: string;
}

export interface ApiResponse<T = unknown> {
  code: number;
  message: string;
  data: T;
  meta: ApiMeta;
}

export interface PaginationMeta {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface PaginatedData<T> {
  items: T[];
  pagination: PaginationMeta;
}

/** Business error thrown when code !== 0 */
export class ApiError extends Error {
  code: number;
  status: number;

  constructor(code: number, message: string, status: number = 400) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}
