import Link from "next/link";

export const metadata = {
  title: "Privacy Policy | JobHunter Agent",
};

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-white dark:bg-zinc-950">
      <main className="mx-auto max-w-3xl px-6 py-20">
        <Link
          href="/"
          className="mb-8 inline-block text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-white"
        >
          &larr; Back to home
        </Link>
        <h1 className="text-4xl font-bold text-zinc-900 dark:text-white mb-2">
          Privacy Policy
        </h1>
        <p className="text-zinc-500 text-sm mb-10">
          Effective Date: March 8, 2026
        </p>

        <div className="space-y-8 text-zinc-600 dark:text-zinc-300 leading-relaxed">
          <section>
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-white mb-3">
              1. Introduction
            </h2>
            <p>
              V2 Software LLC (&ldquo;V2 Software,&rdquo; &ldquo;we,&rdquo;
              &ldquo;us,&rdquo; or &ldquo;our&rdquo;) operates JobHunter Agent
              at jobhunteragent.com (the &ldquo;Service&rdquo;). This Privacy
              Policy describes how we collect, use, and protect information when
              you use the Service.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-white mb-3">
              2. Information We Collect
            </h2>
            <p className="mb-3">
              <strong className="text-zinc-900 dark:text-white">
                Account Information:
              </strong>{" "}
              When you sign up, we collect your name, email address, and
              authentication credentials (via Google OAuth or email/password).
            </p>
            <p className="mb-3">
              <strong className="text-zinc-900 dark:text-white">
                Resume and Career Data:
              </strong>{" "}
              You may upload resumes, job preferences, and career information to
              use the Service. This data is used solely to provide job search
              automation features.
            </p>
            <p className="mb-3">
              <strong className="text-zinc-900 dark:text-white">
                Payment Information:
              </strong>{" "}
              Payment processing is handled by Stripe. We do not store your
              credit card details. Stripe&apos;s privacy policy governs payment
              data handling.
            </p>
            <p>
              <strong className="text-zinc-900 dark:text-white">
                Automatically Collected Information:
              </strong>{" "}
              We collect standard server logs including IP addresses, browser
              type, and pages visited for performance monitoring and security.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-white mb-3">
              3. How We Use Your Information
            </h2>
            <p className="mb-3">We use collected information to:</p>
            <ul className="list-disc pl-6 space-y-1">
              <li>Provide and improve the job search automation Service</li>
              <li>Process payments and manage subscriptions</li>
              <li>Send transactional notifications (email and SMS)</li>
              <li>Monitor and improve Service performance and security</li>
              <li>Comply with legal obligations</li>
            </ul>
            <p className="mt-3">
              We do not sell, rent, or trade your personal information to third
              parties.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-white mb-3">
              4. SMS Communications
            </h2>
            <p>
              If you opt in to SMS notifications, we will send you messages
              about your job search sessions, application status updates, and
              autopilot schedule alerts. You can opt out at any time by
              replying STOP or updating your notification preferences in
              Settings. Message and data rates may apply. Message frequency
              varies based on your usage.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-white mb-3">
              5. Cookies and Tracking
            </h2>
            <p>
              We use essential cookies for authentication and session management.
              We do not use cookies for advertising or behavioral tracking. No
              third-party advertising trackers are present on this Service.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-white mb-3">
              6. Third-Party Services
            </h2>
            <p>
              The Service integrates with third-party providers including
              Stripe (payments), Google (authentication), and Railway (hosting).
              Each provider&apos;s privacy policy governs their respective data
              handling practices.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-white mb-3">
              7. Data Retention
            </h2>
            <p>
              We retain personal information only as long as necessary to
              provide the Service or as required by law. You may request
              deletion of your account and associated data at any time by
              contacting us.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-white mb-3">
              8. Data Security
            </h2>
            <p>
              We implement reasonable technical and organizational measures to
              protect your information against unauthorized access, alteration,
              disclosure, or destruction. All data is encrypted in transit via
              TLS. However, no method of transmission over the Internet is 100%
              secure.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-white mb-3">
              9. Your Rights
            </h2>
            <p>
              Depending on your jurisdiction, you may have the right to access,
              correct, delete, or restrict the processing of your personal data.
              California residents may have additional rights under the CCPA. To
              exercise any of these rights, contact us at the email below.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-white mb-3">
              10. Children&apos;s Privacy
            </h2>
            <p>
              This Service is not directed at individuals under the age of 13.
              We do not knowingly collect personal information from children. If
              we learn that we have inadvertently collected such information, we
              will promptly delete it.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-white mb-3">
              11. Changes to This Policy
            </h2>
            <p>
              We may update this Privacy Policy from time to time. Changes will
              be posted on this page with an updated effective date. Continued
              use of the Service after any modifications constitutes acceptance
              of the revised policy.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-white mb-3">
              12. Contact
            </h2>
            <p>
              For questions or requests regarding this Privacy Policy, contact
              us at{" "}
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
