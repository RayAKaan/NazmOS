export interface ApiError {
  error: boolean;
  code: string;
  message: string;
  detail: unknown;
  timestamp: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  pagination: {
    page: number;
    limit: number;
    total: number;
    total_pages: number;
  };
}
