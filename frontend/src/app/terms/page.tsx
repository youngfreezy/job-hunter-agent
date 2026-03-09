import Link from "next/link";

export const metadata = {
  title: "Terms of Service | JobHunter Agent",
};

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-white dark:bg-zinc-950">
      <main className="mx-auto max-w-3xl px-6 py-20">
        <Link
          href="/"
          className="mb-8 inline-block text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-white"
        >
          &larr; Back to home
        </Link>
        <h1 className="text-4xl font-bold text-zinc-900 dark:text-white mb-2">Terms of Service</h1>
        <p className="text-zinc-500 text-sm mb-10">Effective Date: March 8, 2026</p>

        <div className="space-y-8 text-zinc-600 dark:text-zinc-300 leading-relaxed">
          <section>
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-white mb-3">
              1. Acceptance of Terms
            </h2>
            <p>
              By accessing or using JobHunter Agent at jobhunteragent.com (the
              &ldquo;Service&rdquo;), you agree to be bound by these Terms of Service
              (&ldquo;Terms&rdquo;). If you do not agree to these Terms, do not use the Service. V2
              Software LLC (&ldquo;V2 Software,&rdquo; &ldquo;we,&rdquo; &ldquo;us,&rdquo; or
              &ldquo;our&rdquo;) reserves the right to modify these Terms at any time. Continued use
              of the Service constitutes acceptance of any modifications.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-white mb-3">
              2. Description of Service
            </h2>
            <p>
              JobHunter Agent is an AI-powered job search automation platform that helps users
              discover job listings, tailor resumes, and apply to positions. The Service includes
              features such as automated job discovery, resume tailoring, application submission,
              interview preparation, and career coaching.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-white mb-3">
              3. Account Registration
            </h2>
            <p>
              You must create an account to use the Service. You are responsible for maintaining the
              security of your account credentials and for all activities that occur under your
              account. You agree to provide accurate and complete information during registration.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-white mb-3">
              4. Subscriptions and Payments
            </h2>
            <p>
              The Service offers paid subscription plans. Payment is processed through Stripe. By
              subscribing, you authorize us to charge your payment method on a recurring basis. You
              may cancel your subscription at any time through your account settings. Refunds are
              handled on a case-by-case basis.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-white mb-3">
              5. Acceptable Use
            </h2>
            <p className="mb-3">You agree not to:</p>
            <ul className="list-disc pl-6 space-y-1">
              <li>Use the Service for any unlawful purpose</li>
              <li>Submit false or misleading information in job applications</li>
              <li>Attempt to reverse-engineer, decompile, or disassemble the Service</li>
              <li>Interfere with or disrupt the Service or its infrastructure</li>
              <li>Share your account credentials or allow unauthorized access to your account</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-white mb-3">
              6. Intellectual Property
            </h2>
            <p>
              All content, features, and functionality of the Service &mdash; including text,
              graphics, logos, design, and software &mdash; are the property of V2 Software LLC and
              are protected by applicable intellectual property laws. You retain ownership of any
              content you upload (resumes, personal information).
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-white mb-3">
              7. Disclaimer of Warranties
            </h2>
            <p>
              The Service is provided &ldquo;as is&rdquo; without warranties of any kind, express or
              implied. We do not guarantee that the Service will result in job offers or interviews.
              Job search outcomes depend on many factors outside our control, including employer
              decisions and market conditions.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-white mb-3">
              8. Limitation of Liability
            </h2>
            <p>
              V2 Software shall not be liable for any direct, indirect, incidental, consequential,
              or punitive damages arising from your use of the Service, including but not limited to
              missed job opportunities, application errors, or reliance on AI-generated content.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-white mb-3">
              9. Termination
            </h2>
            <p>
              We reserve the right to suspend or terminate your account at any time for violation of
              these Terms or for any reason at our sole discretion. Upon termination, your right to
              use the Service ceases immediately.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-white mb-3">
              10. Governing Law
            </h2>
            <p>
              These Terms shall be governed by and construed in accordance with the laws of the
              State of California, without regard to its conflict of law provisions. Any disputes
              arising under these Terms shall be subject to the exclusive jurisdiction of the courts
              located in San Francisco County, California.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-white mb-3">
              11. Contact
            </h2>
            <p>
              For questions regarding these Terms, contact us at{" "}
              <a
                href="mailto:support@jobhunteragent.com"
                className="text-blue-600 hover:text-blue-500 dark:text-blue-400 dark:hover:text-blue-300"
              >
                support@jobhunteragent.com
              </a>
              .
            </p>
          </section>
        </div>
      </main>
    </div>
  );
}
