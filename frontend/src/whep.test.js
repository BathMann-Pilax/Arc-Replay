import { describe, expect, it } from "vitest";
import { adresseWhep, strategie } from "./whep";

describe("vue en direct (WHEP)", () => {
  it("passe par le relais nginx /webrtc/", () => {
    expect(adresseWhep("cible")).toBe("/webrtc/cible/whep");
    expect(adresseWhep("vue 1")).toBe("/webrtc/vue%201/whep");
  });
  it("essaie deux fois le WebRTC, puis le HLS en retentant toutes les 30 s", () => {
    expect(strategie(0)).toEqual({ mode: "webrtc", attenteMs: 0 });
    expect(strategie(1)).toEqual({ mode: "webrtc", attenteMs: 2000 });
    expect(strategie(2)).toEqual({ mode: "hls", reessayerWebrtcMs: 30000 });
  });
  it("va directement au HLS sans WebRTC (ancien navigateur)", () => {
    expect(strategie(0, false)).toEqual({ mode: "hls", reessayerWebrtcMs: null });
  });
});
