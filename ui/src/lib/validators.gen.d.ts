// Types for validators.gen.js.
import type { ErrorObject } from "ajv";

export type Validator = ((data: unknown) => boolean) & { errors?: ErrorObject[] | null };
export const guidanceValidator: Validator;
export const indexValidator: Validator;
export const reportValidator: Validator;
