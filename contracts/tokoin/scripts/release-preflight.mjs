import { evaluatePublicTestnetReadiness } from "./release-preflight-lib.mjs";

const result = evaluatePublicTestnetReadiness();
console.log(JSON.stringify(result, null, 2));
if (!result.ready) process.exitCode = 1;
