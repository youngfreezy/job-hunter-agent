import { indeedEasyApplyOnly } from "../../lib/indeed-policy";

export const steps = [
  {
    num: "1",
    title: "Upload & Configure",
    desc: "Browse the product tour below first, or upload your resume and set target roles, locations, salary, and remote preferences.",
  },
  {
    num: "2",
    title: "AI Career Coach",
    desc: "Your AI rewrites your resume as a personal salesperson, scores it, and builds cover letter templates. You approve everything before it goes out.",
  },
  {
    num: "3",
    title: "Discover & Score",
    desc: indeedEasyApplyOnly ? "Discover Indeed Easy Apply roles, review matches, and approve your shortlist. Employer redirects and extra sign-ins are skipped." : "Agents scan Indeed, LinkedIn, Glassdoor, ZipRecruiter, and Google Jobs simultaneously. You choose which roles get your application.",
  },
  {
    num: "4",
    title: "Watch & Apply",
    desc: "Watch the agent apply in real-time. Chat to steer it, or take direct browser control. Get a detailed report with proofs when done.",
  },
];

export const platformHighlights = [
  {
    stat: "15+ hrs/week saved",
    title: "Reclaim your time",
    desc: "Stop copy-pasting the same info into 50 different forms. Your AI handles the repetitive parts while you focus on networking and interview prep.",
  },
  {
    stat: "Every app is tailored",
    title: "No more generic resumes",
    desc: "Each application gets a resume and cover letter customized to the specific role, company, and job description. No two submissions are the same.",
  },
  {
    stat: "You approve everything",
    title: "Full control, zero surprises",
    desc: "Review your optimized resume before anything goes out. Choose exactly which jobs to apply to. Watch applications submit in real time.",
  },
];

export const pricingPacks = [
  {
    name: "Starter",
    apps: 3,
    price: 0,
    priceLabel: "Free",
    perApp: "$0",
    summary: "Try the full platform risk-free.",
    features: [
      "3 free application credits",
      "AI resume optimization",
      indeedEasyApplyOnly ? "Indeed Easy Apply job matching" : "Job matching across 5 boards",
      "Shortlist approval before submission",
      "Download all tailored materials",
    ],
    cta: "Start Free",
    popular: false,
  },
  {
    name: "10 Credits",
    apps: 10,
    price: 24.99,
    priceLabel: "$24.99",
    perApp: "$2.50",
    perDay: "$0.83/day",
    summary: "Perfect first purchase after free trial.",
    features: [
      "10 application credits",
      "Partial attempts only cost 0.5 credits",
      "Cover letter + resume tailored per role",
      "Real-time progress tracking",
      "Full application history",
    ],
    cta: "Get 10 Credits",
    popular: false,
  },
  {
    name: "50 Credits",
    apps: 50,
    price: 99.99,
    priceLabel: "$99.99",
    perApp: "$2.00",
    perDay: "$6.67/day",
    summary: "Best value for serious job searches.",
    features: [
      "50 application credits",
      "Everything in 10 Credits pack",
      "Priority application processing",
      "Direct browser control for complex sites",
      "Save 20% vs 10-credit packs",
    ],
    cta: "Get 50 Credits",
    popular: true,
  },
  {
    name: "Unlimited Monthly",
    apps: -1,
    price: 149.99,
    priceLabel: "$149.99",
    perApp: "unlimited",
    perDay: "$5.00/day",
    summary: "Unlimited applications for active searchers.",
    features: [
      "Up to 100 applications/month",
      "Everything in 50 Credits pack",
      "Cancel or pause anytime",
      "Priority support",
      "Best for 50+ applications/month",
    ],
    cta: "Go Unlimited",
    popular: false,
  },
];

export const faqs = [
  {
    q: "How does JobHunter Agent apply to jobs?",
    a: "Stagehand uses browser automation through Browserbase to fill application forms with your resume and saved answers. Search runs include resume and shortlist review; Quick Apply starts from the job links you explicitly choose. Missing answers appear in the app, and verification may require your input in the live browser.",
  },
  {
    q: "Is my personal data safe?",
    a: "Your selected AI provider processes resume and application content, and Browserbase runs the browser used to apply. Information you submit is shared with the job board and employer. Saved API keys are encrypted. See our Privacy Policy for details about storage and service providers.",
  },
  {
    q: "Does this comply with job site terms of service?",
    a: "Job boards set their own rules for automation. Review the terms of the platform you use; a genuine account or an approval step does not itself guarantee compliance. The app uses the job links, resume, and application facts you provide.",
  },
  {
    q: "What job boards are supported?",
    a: indeedEasyApplyOnly ? "This deployment searches Indeed and applies through Indeed Easy Apply. Employer redirects and additional account sign-ins are skipped. Some Indeed forms still have multiple steps or required questions." : "We currently support LinkedIn, Indeed, Glassdoor, ZipRecruiter, and direct company career pages using Greenhouse, Lever, Workday, Ashby, and iCIMS applicant tracking systems.",
  },
  {
    q: "What if an application fails?",
    a: "Partial attempts \u2014 where your resume was tailored, a cover letter was written, or a form was partially filled \u2014 use only 0.5 credits. You keep all the tailored materials and can apply manually. If a job was skipped entirely (duplicate, already applied), no credits are used.",
  },
  {
    q: "Can I get a refund?",
    a: "Partial attempts are charged at a reduced rate (0.5 credits) because real work was performed \u2014 your resume was tailored and a custom cover letter was generated. For unused credits, contact us within 30 days for a full refund.",
  },
];

export const jsonLd = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "JobHunter Agent",
  applicationCategory: "BusinessApplication",
  operatingSystem: "Web",
  description:
    indeedEasyApplyOnly ? "AI-powered Indeed Easy Apply workflow with resume coaching, shortlist approval, browser visibility, and application status tracking." : "AI-powered job application automation. Searches 5 job boards, tailors resumes per role, and submits applications automatically with human approval checkpoints.",
  offers: [
    {
      "@type": "Offer",
      price: "0",
      priceCurrency: "USD",
      description: "3 free application credits",
    },
    { "@type": "Offer", price: "24.99", priceCurrency: "USD", description: "10 credit pack" },
    { "@type": "Offer", price: "99.99", priceCurrency: "USD", description: "50 credit pack" },
    {
      "@type": "Offer",
      price: "149.99",
      priceCurrency: "USD",
      description: "Unlimited monthly subscription",
    },
  ],
  featureList: [
    "AI resume optimization",
    indeedEasyApplyOnly ? "Indeed Easy Apply discovery" : "Automated job board search across LinkedIn, Indeed, Glassdoor, ZipRecruiter",
    "Per-role resume tailoring",
    "Cover letter generation",
    "Two human approval checkpoints",
    "Real-time application tracking",
    indeedEasyApplyOnly ? "Indeed-hosted applications" : "Support for Greenhouse, Lever, Workday, Ashby ATS platforms",
  ],
};

