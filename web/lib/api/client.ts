import createClient from "openapi-fetch";
import type { paths } from "./types";

const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export const api = createClient<paths>({ baseUrl });

export type Meta = {
  as_of?: string | null;
  data_version?: string | null;
  model_version?: string | null;
  spec_version?: string | null;
  generated_at: string;
  synthetic: boolean;
  disclaimer: string;
};

export type Envelope<T> = { data: T; meta: Meta };

/** RFC 9457 problem+json, as raised by `mq.api.errors` (mq/stale-data, mq/unknown-series, ...). */
export type ApiProblem = {
  type: string;
  title: string;
  status: number;
  detail?: string;
};

export function isApiProblem(err: unknown): err is ApiProblem {
  return typeof err === "object" && err !== null && "type" in err && "status" in err;
}
