// Copyright (c) 2026 V2 Software LLC. All rights reserved.

/** Auth entry points. Only these two pages exist; old paths redirect here (next.config.mjs). */
export const ROUTES = {
  login: "/auth/login",
  signup: "/auth/signup",
} as const;
