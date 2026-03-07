import NextAuth, { type NextAuthOptions } from "next-auth";
import GoogleProvider from "next-auth/providers/google";
import CredentialsProvider from "next-auth/providers/credentials";

// Credentials auth is for local/dev-only bootstrapping unless explicitly enabled.
const allowCredentialsAuth =
  process.env.NODE_ENV !== "production" ||
  process.env.ENABLE_CREDENTIALS_AUTH === "true";

// Only include Google provider when credentials are configured
const providers: NextAuthOptions["providers"] = [];
if (process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_ID !== "xxx") {
  providers.push(
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET || "",
      authorization: {
        params: {
          scope:
            "openid email profile https://www.googleapis.com/auth/gmail.readonly",
          access_type: "offline",
          prompt: "consent",
        },
      },
    })
  );
}

// Email/password — dev mode accepts any email/password
providers.push(
  CredentialsProvider({
    name: "Email",
    credentials: {
      email: { label: "Email", type: "email", placeholder: "you@example.com" },
      password: { label: "Password", type: "password" },
    },
    async authorize(credentials) {
      if (!allowCredentialsAuth) {
        return null;
      }
      // TODO: Replace with real DB lookup in Phase 4.
      if (credentials?.email && credentials?.password) {
        return {
          id: "dev-user-1",
          email: credentials.email,
          name: credentials.email.split("@")[0],
        };
      }
      return null;
    },
  })
);

const authOptions: NextAuthOptions = {
  providers,
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
      }
      // Capture Google OAuth tokens on initial sign-in
      if (account?.provider === "google") {
        token.googleAccessToken = account.access_token;
        token.googleRefreshToken = account.refresh_token;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        const u = session.user as Record<string, unknown>;
        u.id = token.userId;
        u.googleAccessToken = token.googleAccessToken;
      }
      return session;
    },
  },
};

const handler = NextAuth(authOptions);
export { handler as GET, handler as POST };
