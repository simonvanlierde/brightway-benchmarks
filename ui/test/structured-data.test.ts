import { expect, it } from "vitest";
import codemeta from "../../codemeta.json";
import { softwareJsonLd } from "../src/lib/structured-data";

it("maps maintained project metadata to Schema.org software", () => {
  expect(JSON.parse(softwareJsonLd())).toEqual({
    "@context": "https://schema.org",
    "@type": "SoftwareSourceCode",
    "@id": codemeta.codeRepository,
    name: codemeta.name,
    description: codemeta.description,
    codeRepository: codemeta.codeRepository,
    license: codemeta.license,
    programmingLanguage: codemeta.programmingLanguage,
    author: codemeta.author.map((author) => ({
      "@type": "Person",
      "@id": author["@id"],
      name: `${author.givenName} ${author.familyName}`,
    })),
  });
});

it("cannot close the HTML script element through a metadata value", () => {
  const description = 'A </script><script>alert("metadata")</script> example';
  const serialized = softwareJsonLd({ ...codemeta, description });
  expect(serialized).not.toContain("<");
  expect(JSON.parse(serialized).description).toBe(description);
});
