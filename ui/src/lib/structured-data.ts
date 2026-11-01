import codemeta from "../../../codemeta.json";

export function softwareJsonLd(source = codemeta): string {
  return JSON.stringify({
    "@context": "https://schema.org",
    "@type": "SoftwareSourceCode",
    "@id": source.codeRepository,
    name: source.name,
    description: source.description,
    codeRepository: source.codeRepository,
    license: source.license,
    programmingLanguage: source.programmingLanguage,
    author: source.author.map((author) => ({
      "@type": "Person",
      "@id": author["@id"],
      name: `${author.givenName} ${author.familyName}`,
    })),
  }).replaceAll("<", "\\u003c");
}
