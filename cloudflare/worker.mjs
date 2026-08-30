import { Container } from "cloudflare:workers";

/**
 * Public HTTP entry point for the StreamBridge FastAPI container.
 * A single named instance keeps the HLS proxy cache warm between requests.
 */
export class StreamBridgeContainer extends Container {
  defaultPort = 8080;
  sleepAfter = "10m";
}

export default {
  async fetch(request, env) {
    const instance = env.STREAMBRIDGE.getByName("primary");
    return instance.fetch(request);
  },
};
