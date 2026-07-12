// Clean: all HTTP access flows through the contract-driven HttpClient.
import { httpClient } from "../http/http-client";
import { usersContract } from "../contracts/users";

export async function getUser(id: string) {
  // No raw fetch(): the governed client applies contracts + telemetry.
  return httpClient.get(usersContract.byId, { id });
}
