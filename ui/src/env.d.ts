interface ImportMetaEnv {
  /** Where index.json lives: an absolute URL, or a path relative to the page. */
  readonly PUBLIC_DATA_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
