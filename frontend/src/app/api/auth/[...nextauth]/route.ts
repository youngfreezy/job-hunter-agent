// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import NextAuth, { type NextAuthOptions } from "next-auth";
import GoogleProvider from "next-auth/providers/google";
import CredentialsProvider from "next-auth/providers/credentials";
import { demoAuthEnabled, validDemoCredentials } from "@/lib/local-demo-auth";

const authOptions: NextAuthOptions = {
  providers: [
    ...(demoAuthEnabled() ? [CredentialsProvider({
      name: "Local demo",
      credentials: { email: { label: "Email", type: "email" }, password: { label: "Password", type: "password" } },
      async authorize(credentials) {
        if (!validDemoCredentials(credentials?.email ?? "", credentials?.password ?? "")) return null;
        return { id: "local-demo", email: process.env.LOCAL_DEMO_EMAIL!, name: "Fareez (local demo)" };
      },
    })] : []),
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID ?? "missing",
      clientSecret: process.env.GOOGLE_CLIENT_SECRET ?? "missing",
      authorization: {
        params: {
          scope: process.env.ENABLE_GMAIL_VERIFICATION === "true"
            ? "openid email profile https://www.googleapis.com/auth/gmail.readonly"
            : "openid email profile",
          access_type: "offline",
          prompt: "consent",
        },
      },
    }),
  ],
  session: {
    strategy: "jwt",
    maxAge: 7 * 24 * 60 * 60, // 7 days
  },
  pages: {
    signIn: "/auth/login",
    newUser: "/session/new",
  },
  callbacks: {
    async jwt({ token, user, account }) {
      if (user) {
        token.userId = user.id;
        if (user.email) token.email = user.email;
        if (user.name) token.name = user.name;
      }
      // Capture Google OAuth tokens on initial sign-in
      if (account?.provider === "google" && account.scope?.includes("gmail.readonly")) {
        token.googleAccessToken = account.access_token;
        token.googleRefreshToken = account.refresh_token;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        const u = session.user as Record<string, unknown>;
        u.id = token.userId;
        // Google OAuth tokens are intentionally NOT exposed to the client.
        // Server-side code uses getToken() to access them (see /api/auth/gmail-token).
      }
      return session;
    },
  },
};

const handler = NextAuth(authOptions);
export { handler as GET, handler as POST };
