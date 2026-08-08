const appUrl = process.env.NEXT_PUBLIC_APP_URL || "https://app.nazm.ai";

const organizationLd = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "Nazmak",
  url: "https://nazm.ai",
  logo: `${appUrl}/icon.png`,
  sameAs: ["https://x.com/nazmak_ai"],
  contactPoint: {
    "@type": "ContactPoint",
    contactType: "support",
    url: "https://nazm.ai",
  },
};

const softwareLd = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "NazmOS",
  applicationCategory: "BusinessApplication",
  operatingSystem: "Any",
  url: appUrl,
  provider: {
    "@type": "Organization",
    name: "Nazmak",
  },
  offers: {
    "@type": "Offer",
    price: "0",
    priceCurrency: "SAR",
    description: "Free Money Audit tier",
  },
  description:
    "NazmOS is the inventory intelligence operating system for e-commerce and retail teams. Forecast demand, audit margins, orchestrate suppliers, and automate replenishment across every channel.",
};

const websiteLd = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  name: "NazmOS",
  url: appUrl,
  potentialAction: {
    "@type": "SearchAction",
    target: `${appUrl}/dashboard`,
    "query-input": "required name=search_term_string",
  },
};

export function StructuredData() {
  return (
    <>
      <script
        id="schema-organization"
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(organizationLd) }}
      />
      <script
        id="schema-software"
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(softwareLd) }}
      />
      <script
        id="schema-website"
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(websiteLd) }}
      />
    </>
  );
}
