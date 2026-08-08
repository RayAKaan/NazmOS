export const ACCESS_COOKIE = "nazm_access";
export const REFRESH_COOKIE = "nazm_refresh";
export const SESSION_COOKIE = "nazm_session";

export const ACCESS_MAX_AGE = 15 * 60;
export const REFRESH_MAX_AGE = 30 * 24 * 60 * 60;

export function cookieOptions(maxAge: number, path = "/") {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path,
    maxAge,
  };
}
