// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { withAuth } from "next-auth/middleware";

export default withAuth({
  pages: {
    signIn: "/auth/login",
  },
});

// Protect dashboard and session routes — landing page and auth are public
export const config = {
  matcher: [
    "/dashboard/:path*", "/session/:path*", "/account/:path*", "/settings/:path*",
    "/billing/:path*", "/developer/:path*", "/apply/:path*", "/quick-apply/:path*",
    "/history/:path*", "/autopilot/:path*", "/interview-prep/:path*",
    "/career-pivot/:path*", "/freelance/:path*", "/marketplace/:path*",
  ],
};
