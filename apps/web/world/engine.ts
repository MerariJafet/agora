// PixiJS world engine (S3-T08..T14, T19, ADR-0016).
//
// Ownership: this file renders. It never fetches, never posts, and never
// invents authoritative state — it reads the WorldStore and animates.
// The server sees zero output from anything here (no coordinates, no camera,
// no frames).

import {
  Application,
  Container,
  Graphics,
  Text,
  TextStyle,
  type FederatedPointerEvent,
} from "pixi.js";
import { drawAvatar } from "./avatar-draw";
import type { WorldStore } from "./store";
import type { Landmark } from "./types";

const COLORS = {
  bg: 0x0b0e14,
  grid: 0x1a2030,
  active: 0xd4a24a,
  coming: 0x4aa3c4,
  locked: 0x8a94ad,
  text: 0xe8ecf4,
  muted: 0x8a94ad,
};

const MOVE_SPEED = 210; // world units / second (cosmetic only)

export interface EngineCallbacks {
  onSelectAgent(agentId: string): void;
  onSelectLandmark(landmarkId: string): void;
}

interface AgentNode {
  container: Container;
  avatarKey: string;
  label: Text;
  effect: Graphics;
  detail: "near" | "mid" | "far";
}

export class WorldEngine {
  private app: Application | null = null;
  private world = new Container();
  private layers = {
    terrain: new Container(),
    landmarks: new Container(),
    agents: new Container(),
    effects: new Container(),
  };
  private nodes = new Map<string, AgentNode>();
  private clusters = new Container();
  private lastVersion = -1;
  private frames = 0;
  private canvasHost: HTMLElement | null = null;
  private zoom = 0.5;
  private reducedMotion = false;
  private destroyed = false;

  constructor(
    private store: WorldStore,
    private callbacks: EngineCallbacks,
  ) {}

  get application(): Application | null {
    return this.app;
  }

  get currentZoom(): number {
    return this.zoom;
  }

  /** Detail mode currently in use — exposed for tests/telemetry. */
  detailMode(): "near" | "mid" | "far" {
    const lod = this.store.manifest?.lod;
    if (!lod) return "near";
    if (this.zoom < lod.far_zoom_below) return "far";
    if (this.zoom < lod.mid_zoom_below) return "mid";
    return "near";
  }

  async init(canvasHost: HTMLElement, options?: { reducedMotion?: boolean }) {
    this.reducedMotion = options?.reducedMotion ?? false;
    const app = new Application();
    // Async init is required in Pixi v8. WebGL is the compatibility baseline;
    // Pixi falls back automatically if the preferred backend is unavailable.
    await app.init({
      preference: "webgl",
      background: COLORS.bg,
      antialias: true,
      resizeTo: canvasHost,
      autoDensity: true,
      resolution: Math.min(globalThis.devicePixelRatio ?? 1, 2),
      // Own ticker: the engine controls exactly when frames happen.
      sharedTicker: false,
    });
    if (this.destroyed) {
      app.destroy(true, { children: true });
      return;
    }
    this.app = app;
    this.canvasHost = canvasHost;
    // Guard against double-canvas during React strict-mode/hot reload.
    canvasHost.replaceChildren(app.canvas);
    app.canvas.setAttribute("aria-hidden", "true"); // DOM sidebar is the a11y surface

    this.world.addChild(
      this.layers.terrain,
      this.layers.landmarks,
      this.layers.agents,
      this.layers.effects,
    );
    this.layers.agents.addChild(this.clusters);
    app.stage.addChild(this.world);
    app.stage.eventMode = "static";
    app.stage.hitArea = { contains: () => true } as never;

    this.buildTerrain();
    this.buildLandmarks();
    this.attachCamera(app);
    this.centerOn(0, 0);

    app.ticker.add((ticker) => this.frame(ticker.deltaMS));
    document.addEventListener("visibilitychange", this.onVisibility);
  }

  destroy() {
    this.destroyed = true;
    document.removeEventListener("visibilitychange", this.onVisibility);
    this.nodes.clear();
    if (this.app) {
      this.app.destroy(true, { children: true });
      this.app = null;
    }
  }

  /** Hidden tabs must not burn CPU/GPU (efficiency invariant). */
  private onVisibility = () => {
    if (!this.app) return;
    if (document.hidden) this.app.ticker.stop();
    else this.app.ticker.start();
  };

  // ---- static scene ------------------------------------------------------

  private buildTerrain() {
    const bounds = this.store.manifest?.bounds;
    if (!bounds) return;
    const g = new Graphics();
    const step = 130;
    for (let x = bounds.min_x; x <= bounds.max_x; x += step) {
      g.moveTo(x, bounds.min_y).lineTo(x, bounds.max_y);
    }
    for (let y = bounds.min_y; y <= bounds.max_y; y += step) {
      g.moveTo(bounds.min_x, y).lineTo(bounds.max_x, y);
    }
    g.stroke({ color: COLORS.grid, width: 1, alpha: 0.5 });

    const paths = new Graphics();
    this.store.manifest?.nav_edges.forEach(([a, b]) => {
      const from = this.store.landmark(a);
      const to = this.store.landmark(b);
      if (from && to) paths.moveTo(from.x, from.y).lineTo(to.x, to.y);
    });
    paths.stroke({ color: COLORS.grid, width: 3, alpha: 0.9 });

    this.layers.terrain.removeChildren();
    this.layers.terrain.addChild(g, paths);
    // Terrain never changes: caching it as a texture avoids re-rasterizing
    // thousands of grid segments every frame.
    this.layers.terrain.cacheAsTexture(true);
  }

  private buildLandmarks() {
    this.layers.landmarks.removeChildren();
    this.store.manifest?.landmarks.forEach((landmark) => {
      this.layers.landmarks.addChild(this.buildLandmark(landmark));
    });
  }

  private buildLandmark(landmark: Landmark): Container {
    const container = new Container();
    container.position.set(landmark.x, landmark.y);
    container.eventMode = "static";
    container.cursor = "pointer";
    container.on("pointertap", () => this.callbacks.onSelectLandmark(landmark.id));

    const color =
      landmark.state === "ACTIVE" ? COLORS.active
      : landmark.state === "COMING_SOON" ? COLORS.coming
      : COLORS.locked;
    const alpha = landmark.state === "ACTIVE" ? 1 : 0.55;
    const g = new Graphics();
    g.circle(0, 0, landmark.radius).fill({ color, alpha: 0.06 });
    if (landmark.state === "LOCKED") {
      // Dashed ring: visibly present, honestly not open.
      for (let i = 0; i < 32; i += 2) {
        const a0 = (Math.PI / 16) * i;
        g.arc(0, 0, landmark.radius, a0, a0 + Math.PI / 16);
      }
      g.stroke({ color, width: 2, alpha });
    } else {
      g.circle(0, 0, landmark.radius).stroke({ color, width: 2, alpha });
    }
    if (landmark.state === "ACTIVE") {
      g.circle(0, 0, landmark.radius * 0.5).stroke({ color, width: 1, alpha: 0.25 });
    }

    const title = new Text({
      text: landmark.name.toUpperCase(),
      style: new TextStyle({
        fill: color, fontSize: 20, fontFamily: "ui-sans-serif, system-ui",
        letterSpacing: 3, fontWeight: "600",
      }),
    });
    title.anchor.set(0.5);
    title.position.set(0, -landmark.radius - 26);
    title.alpha = alpha;

    const badge = new Text({
      text: landmark.state === "ACTIVE" ? "" :
        landmark.state === "COMING_SOON" ? "COMING SOON" : "LOCKED",
      style: new TextStyle({ fill: color, fontSize: 12, letterSpacing: 2 }),
    });
    badge.anchor.set(0.5);
    badge.position.set(0, -landmark.radius - 6);
    badge.alpha = 0.85;

    container.addChild(g, title, badge);
    return container;
  }

  // ---- camera ------------------------------------------------------------

  private attachCamera(app: Application) {
    let dragging = false;
    let lastX = 0;
    let lastY = 0;

    app.stage.on("pointerdown", (event: FederatedPointerEvent) => {
      dragging = true;
      lastX = event.globalX;
      lastY = event.globalY;
    });
    const end = () => { dragging = false; };
    app.stage.on("pointerup", end);
    app.stage.on("pointerupoutside", end);
    app.stage.on("pointermove", (event: FederatedPointerEvent) => {
      if (!dragging) return;
      this.world.position.x += event.globalX - lastX;
      this.world.position.y += event.globalY - lastY;
      lastX = event.globalX;
      lastY = event.globalY;
    });
    app.canvas.addEventListener("wheel", (event) => {
      event.preventDefault();
      this.setZoom(this.zoom * (event.deltaY < 0 ? 1.12 : 0.89));
    }, { passive: false });
  }

  setZoom(zoom: number) {
    this.zoom = Math.min(1.6, Math.max(0.14, zoom));
    this.world.scale.set(this.zoom);
  }

  centerOn(x: number, y: number) {
    const app = this.app;
    if (!app) return;
    this.world.position.set(
      app.screen.width / 2 - x * this.zoom,
      app.screen.height / 2 - y * this.zoom,
    );
  }

  focusLandmark(landmarkId: string) {
    const landmark = this.store.landmark(landmarkId);
    if (!landmark) return;
    this.setZoom(0.75);
    this.centerOn(landmark.x, landmark.y);
  }

  focusAgent(agentId: string) {
    const visual = this.store.visuals.get(agentId);
    if (!visual) return;
    this.setZoom(1.0);
    this.centerOn(visual.x, visual.y);
  }

  // ---- per-frame ---------------------------------------------------------

  private frame(deltaMS: number) {
    if (!this.app) return;
    this.frames += 1;
    // Cheap, test-readable telemetry: the counter advances only while the
    // private ticker runs, so a hidden tab visibly freezes it.
    this.canvasHost?.setAttribute("data-world-frames", String(this.frames));
    this.canvasHost?.setAttribute("data-world-detail", this.detailMode());
    const detail = this.detailMode();
    if (this.store.version !== this.lastVersion) {
      this.syncNodes(detail);
      this.lastVersion = this.store.version;
    }
    this.animate(deltaMS, detail);
  }

  private avatarKey(agentId: string): string {
    const agent = this.store.agents.get(agentId);
    return agent ? JSON.stringify(agent.avatar) : "";
  }

  private syncNodes(detail: "near" | "mid" | "far") {
    // Far mode: no per-agent nodes at all — aggregate clusters from semantic
    // presence counts (ADR-0018). Population, not simulated objects.
    if (detail === "far") {
      this.nodes.forEach((node) => node.container.destroy({ children: true }));
      this.nodes.clear();
      this.renderClusters();
      return;
    }
    this.clusters.removeChildren();

    const alive = new Set<string>();
    this.store.agents.forEach((agent) => {
      alive.add(agent.agent_id);
      let node = this.nodes.get(agent.agent_id);
      const key = this.avatarKey(agent.agent_id);
      if (node && (node.avatarKey !== key || node.detail !== detail)) {
        node.container.destroy({ children: true });
        this.nodes.delete(agent.agent_id);
        node = undefined;
      }
      if (!node) {
        const container = new Container();
        const sprite = drawAvatar(agent.avatar);
        if (detail === "mid") sprite.scale.set(0.7);
        const label = new Text({
          text: agent.name,
          style: new TextStyle({
            fill: COLORS.text, fontSize: 13, fontFamily: "ui-sans-serif, system-ui",
          }),
        });
        label.anchor.set(0.5);
        label.position.set(0, 34);
        label.visible = detail === "near";
        const effect = new Graphics();
        effect.position.set(0, -40);
        container.addChild(sprite, label, effect);
        container.eventMode = detail === "near" ? "static" : "none";
        container.cursor = "pointer";
        container.on("pointertap", () => this.callbacks.onSelectAgent(agent.agent_id));
        this.layers.agents.addChild(container);
        node = { container, avatarKey: key, label, effect, detail };
        this.nodes.set(agent.agent_id, node);
      }
    });
    this.nodes.forEach((node, agentId) => {
      if (!alive.has(agentId)) {
        node.container.destroy({ children: true });
        this.nodes.delete(agentId);
      }
    });
  }

  private renderClusters() {
    this.clusters.removeChildren();
    const counts = this.store.populationBySpace();
    counts.forEach((count, spaceId) => {
      const landmark = this.store.landmarkForSpace(spaceId);
      if (!landmark) return;
      const radius = Math.min(70, 16 + Math.sqrt(count) * 7);
      const cluster = new Container();
      cluster.position.set(landmark.x, landmark.y);
      const g = new Graphics()
        .circle(0, 0, radius)
        .fill({ color: COLORS.active, alpha: 0.22 })
        .circle(0, 0, radius)
        .stroke({ color: COLORS.active, width: 2, alpha: 0.6 });
      const label = new Text({
        text: `${count}`,
        style: new TextStyle({ fill: COLORS.text, fontSize: 22, fontWeight: "600" }),
      });
      label.anchor.set(0.5);
      cluster.addChild(g, label);
      this.clusters.addChild(cluster);
    });
  }

  private animate(deltaMS: number, detail: "near" | "mid" | "far") {
    if (detail === "far") return;
    const seconds = deltaMS / 1000;
    this.store.visuals.forEach((visual, agentId) => {
      const node = this.nodes.get(agentId);
      if (!node) return;
      const agent = this.store.agents.get(agentId);

      // Walk the local path (cosmetic; derived from a semantic transition).
      let waypoint = visual.path[0] ?? { x: visual.targetX, y: visual.targetY };
      const dx = waypoint.x - visual.x;
      const dy = waypoint.y - visual.y;
      const distance = Math.hypot(dx, dy);
      if (distance > 2) {
        const step = Math.min(distance, MOVE_SPEED * seconds * (this.reducedMotion ? 4 : 1));
        visual.x += (dx / distance) * step;
        visual.y += (dy / distance) * step;
      } else if (visual.path.length) {
        visual.path.shift();
        waypoint = visual.path[0] ?? { x: visual.targetX, y: visual.targetY };
      }

      visual.phase += seconds * 2.2;
      const bob = this.reducedMotion ? 0 : Math.sin(visual.phase) * 1.6;
      node.container.position.set(visual.x, visual.y + bob);

      if (visual.speaking > 0) visual.speaking -= deltaMS;
      this.drawActivityEffect(node, agent?.activity ?? "idle", visual, detail);
    });
  }

  private drawActivityEffect(
    node: AgentNode,
    activity: string,
    visual: { phase: number; speaking: number },
    detail: "near" | "mid",
  ) {
    const g = node.effect;
    g.clear();
    if (visual.speaking > 0) {
      g.roundRect(-9, -6, 18, 12, 6).fill({ color: COLORS.active, alpha: 0.9 });
      g.circle(-3, 0, 1.3).fill({ color: COLORS.bg });
      g.circle(0, 0, 1.3).fill({ color: COLORS.bg });
      g.circle(3, 0, 1.3).fill({ color: COLORS.bg });
      return;
    }
    if (detail === "mid") {
      // Reduced effects at distance: a single dot conveys "doing something".
      if (activity !== "idle" && activity !== "offline") {
        g.circle(0, 0, 2.5).fill({ color: COLORS.coming, alpha: 0.8 });
      }
      return;
    }
    const pulse = this.reducedMotion ? 1 : 0.75 + Math.sin(visual.phase * 1.5) * 0.25;
    switch (activity) {
      case "discussing":
      case "debating": {
        const size = activity === "debating" ? 7 : 5;
        g.circle(0, 0, size * pulse).stroke({ color: COLORS.active, width: 2, alpha: 0.85 });
        break;
      }
      case "reading":
      case "reviewing":
        g.roundRect(-7, -5, 14, 10, 2).fill({ color: COLORS.coming, alpha: 0.55 });
        g.moveTo(-4, -1).lineTo(4, -1).moveTo(-4, 2).lineTo(2, 2)
          .stroke({ color: COLORS.bg, width: 1 });
        break;
      case "researching":
        g.arc(0, 0, 10 * pulse, -0.6, 0.6).stroke({ color: 0x4ac48a, width: 2, alpha: 0.8 });
        break;
      case "computing":
        for (let i = 0; i < 3; i += 1) {
          g.rect(-7 + i * 5, -4 - (i === 1 ? 3 : 0) * pulse, 3, 8)
            .fill({ color: 0x7b6ff0, alpha: 0.85 });
        }
        break;
      case "writing":
        g.moveTo(-6, 4).lineTo(6, -6).stroke({ color: COLORS.text, width: 2, alpha: 0.8 });
        g.circle(6, -6, 1.8).fill({ color: COLORS.active });
        break;
      case "building":
        g.star(0, 0, 4, 7 * pulse, 3).fill({ color: 0xd4a24a, alpha: 0.85 });
        break;
      case "exploring":
        g.circle(0, 0, 3).fill({ color: COLORS.muted, alpha: 0.7 });
        g.arc(0, 0, 9, -0.4, 0.4).stroke({ color: COLORS.muted, width: 1.5, alpha: 0.5 });
        break;
      case "error":
        g.circle(0, 0, 6).stroke({ color: 0xe0596a, width: 2, alpha: 0.9 });
        g.moveTo(0, -3).lineTo(0, 1).moveTo(0, 3).lineTo(0, 3.6)
          .stroke({ color: 0xe0596a, width: 2 });
        break;
      default:
        break; // idle: the body's ambient bob is the animation
    }
  }
}
