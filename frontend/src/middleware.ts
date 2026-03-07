import { withAuth } from "next-auth/middleware";

const E2E_AUTH_COOKIE = "jobhunter_test_bypass";

export default withAuth({
  pages: {
    signIn: "/auth/login",
  },
  callbacks: {
    authorized: ({ req, token }) => {
      const hasBypassCookie =
        process.env.NODE_ENV !== "production" &&
        req.cookies.get(E2E_AUTH_COOKIE)?.value === "1";
      return hasBypassCookie || !!token;
    },
  },
});

// Protect dashboard and session routes — landing page and auth are public
export const config = {
  matcher: ["/dashboard/:path*", "/session/:path*"],
};
