// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { CompanySection } from "@/components/landing/CompanySection";
import { jsonLd } from "@/components/landing/content";
import { FinalCallToAction } from "@/components/landing/FinalCallToAction";
import { FrequentlyAskedQuestions } from "@/components/landing/FrequentlyAskedQuestions";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { InfrastructureSection } from "@/components/landing/InfrastructureSection";
import { LandingHero } from "@/components/landing/LandingHero";
import { LandingNavigation } from "@/components/landing/LandingNavigation";
import { PlatformHighlights } from "@/components/landing/PlatformHighlights";
import { PricingSection } from "@/components/landing/PricingSection";
import { ProductTour } from "@/components/landing/ProductTour";
import { SearchCostSection } from "@/components/landing/SearchCostSection";
import { SecuritySection } from "@/components/landing/SecuritySection";
import { SupportedPlatforms } from "@/components/landing/SupportedPlatforms";
import { TermsSection } from "@/components/landing/TermsSection";
import { TrustBar } from "@/components/landing/TrustBar";
import { WaitlistBanner } from "@/components/landing/WaitlistBanner";
import { WorkflowComparison } from "@/components/landing/WorkflowComparison";
import { WorkflowFeatures } from "@/components/landing/WorkflowFeatures";

export default function Home() {
  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-950 dark:bg-zinc-950 dark:text-white">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <WaitlistBanner />
      <LandingNavigation />
      <LandingHero />
      <TrustBar />
      <WorkflowFeatures />
      <WorkflowComparison />
      <PlatformHighlights />
      <HowItWorks />
      <ProductTour />
      <SupportedPlatforms />
      <SearchCostSection />
      <PricingSection />
      <SecuritySection />
      <InfrastructureSection />
      <CompanySection />
      <TermsSection />
      <FrequentlyAskedQuestions />
      <FinalCallToAction />
    </div>
  );
}
