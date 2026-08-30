import { Container, getContainer } from "@cloudflare/containers";

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
    return getContainer(env.STREAMBRIDGE, "primary").fetch(request);
  },
};
