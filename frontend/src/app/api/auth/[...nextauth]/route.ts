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

export const authOptions: NextAuthOptions = {
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
    async jwt({ token, user }) {
      if (user) {
        token.userId = user.id;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        (session.user as Record<string, unknown>).id = token.userId;
      }
      return session;
    },
  },
};

const handler = NextAuth(authOptions);
export { handler as GET, handler as POST };
